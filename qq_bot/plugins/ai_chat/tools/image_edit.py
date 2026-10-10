"""图像编辑工具（图生图）：把群聊/私聊里的"改图"需求落到 DashScope 图像编辑模型。

三段职责分离（对齐 interact_with_member 的思路）：
  ① 主对话模型负责"抽取"——它能看到图片，判定这是改图需求并给出图片序号与修改意图；
  ② 本工具做确定性的事——序号校验、限流、尺寸推算、调用传输层、产出出栈；
  ③ 指令本身由隔离的 ImageEditAgent 精修（补齐"保持面部/发型/背景不变"这类约束）。

图片句柄来自 current_images（handler 下载图片后写入）；产出写入
current_edited_images，由 handler 收尾统一发图——工具作用域里没有 matcher，
不能自己发消息（同 docs/note.md §61.2 第 4 条）。
"""

import io
import logging
import time
from datetime import datetime
from typing import ClassVar
from zoneinfo import ZoneInfo

from nonebot import get_plugin_config

from qq_bot.agents.image_edit_agent import ImageEditAgent
from qq_bot.ai.image_edit_client import ImageEditError
from qq_bot.ai.types import ImageData
from qq_bot.plugins.ai_chat import token_usage
from qq_bot.plugins.ai_chat.client_factory import (
    get_client_for_model,
    get_image_edit_client,
)
from qq_bot.plugins.ai_chat.config import AiChatConfig
from qq_bot.plugins.ai_chat.session_store import get_session_model
from qq_bot.plugins.ai_chat.tools.context import (
    current_edited_images,
    current_images,
    current_scope,
    current_send_msg,
)
from qq_bot.plugins.ai_chat.tools.registry import TOOLS, register_tool

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("Asia/Shanghai")

# 官方限制：3.0 系列图生图支持 1-3 张输入图
_MAX_INPUT_IMAGES = 3

# Agent 精修失败时返回的标记（base.execute 会把 fail_msg 拼进返回串）
_REFINE_FAIL_MARK = "（图片编辑指令精修失败）"
_GENERIC_FAIL = "AI暂时无法响应"

# 产出尺寸约束：官方要求像素面积 512*512 ~ 2048*2048、比例 1:8 ~ 8:1
_SIZE_MIN_SIDE = 512
_SIZE_MAX_SIDE = 2048
_SIZE_STEP = 16
# 接口允许的宽高比范围 1:8 ~ 8:1；超出时不再自作主张，交服务端决定
_RATIO_LIMIT = 8

# 序号校验失败时给出的提示模板
_INPUT_HINT = "本条消息共 {total} 张图，序号应为 1-{total}。"


class _RateState:
    """进程内限流状态。

    只用于防误触与防连点，**不是计费依据**（重启即清零）；
    真实费用以阿里云控制台账单为准。
    """

    last_at: ClassVar[dict[str, float]] = {}
    counts: ClassVar[dict[str, int]] = {}
    day: str = ""


_rate = _RateState()


def _today() -> str:
    return datetime.now(_TZ).strftime("%Y-%m-%d")


def _session_id(scope: str) -> str:
    """scope（groups/{gid}/{uid} 或 private/{uid}）→ 会话 ID"""
    kind, _, rest = scope.partition("/")
    first = rest.split("/", 1)[0]
    if kind == "groups" and first:
        return f"group_{first}"
    if kind == "private" and first:
        return f"user_{first}"
    return ""


def _requester_uid(scope: str) -> str:
    """scope → 发起人 QQ 号（限流按用户维度计）"""
    kind, _, rest = scope.partition("/")
    if kind == "groups":
        return rest.partition("/")[2]
    if kind == "private":
        return rest.split("/", 1)[0]
    return ""


def _fit_size(width: int, height: int) -> str:
    """把长宽约束进接口允许的区间，返回 "宽*高"；无法满足时返回空串。

    约束：长边 ≤2048、总面积 ≥512²、宽高比 1:8 ~ 8:1。
    比例超出范围（如 1:500 的长条图）时不硬凑——硬凑必然违反另一项约束，
    此时返回空串让服务端自己决定更安全。
    """
    shorter = max(1, min(width, height))
    longer = max(width, height)
    if longer / shorter > _RATIO_LIMIT:
        return ""

    if longer > _SIZE_MAX_SIDE:
        scale = _SIZE_MAX_SIDE / longer
        width, height = round(width * scale), round(height * scale)
    # 面积不足下限时等比放大，但放大后长边仍不得越过上限
    if width * height < _SIZE_MIN_SIDE * _SIZE_MIN_SIDE:
        up = ((_SIZE_MIN_SIDE * _SIZE_MIN_SIDE) / (width * height)) ** 0.5
        up = min(up, _SIZE_MAX_SIDE / max(width, height))
        width, height = round(width * up), round(height * up)

    w = max(_SIZE_STEP, (width // _SIZE_STEP) * _SIZE_STEP)
    h = max(_SIZE_STEP, (height // _SIZE_STEP) * _SIZE_STEP)
    return f"{w}*{h}"


def _target_size(base: ImageData, config: AiChatConfig) -> str:
    """推算输出尺寸：配置优先；留空则按"被修改的原图"尺寸推算。

    为什么显式推尺寸：多图输入时输出比例可能随图序变化，若交给服务端自动决定，
    双图场景下产出可能跟着参照图的比例走，把角色拉变形（见 note §73）。
    解不出来返回空串，由服务端自己决定。
    """
    configured = config.image_edit_size.strip()
    if configured:
        return configured
    try:
        from PIL import Image

        with Image.open(io.BytesIO(base.data)) as img:
            return _fit_size(int(img.width), int(img.height))
    except Exception:  # noqa: BLE001  Pillow 缺失/解码失败 → 交给服务端决定
        logger.debug("推算图像编辑输出尺寸失败，改为服务端自动决定", exc_info=True)
        return ""


def _quota_block(uid: str, config: AiChatConfig) -> str:
    """限流校验：通过返回空串，被拦返回可读原因。

    日计数按天惰性重置；冷却按用户维度，避免同一人连点烧钱。
    """
    today = _today()
    if _rate.day != today:
        _rate.day = today
        _rate.counts.clear()

    cooldown = config.image_edit_cooldown_seconds
    now = time.monotonic()
    last = _rate.last_at.get(uid, 0.0)
    if cooldown > 0 and now - last < cooldown:
        wait = int(cooldown - (now - last)) + 1
        return f"改图太频繁了，请等 {wait} 秒后再试。"

    cap = config.image_edit_max_per_user_per_day
    used = _rate.counts.get(uid, 0)
    if cap > 0 and used >= cap:
        return f"你今天改图已达上限（{cap} 次），明天再来吧。"

    _rate.last_at[uid] = now
    _rate.counts[uid] = used + 1
    return ""


def _validate(
    images: list[ImageData],
    base_image: int,
    references: list[int],
    config: AiChatConfig,
    uid: str,
) -> str:
    """入口校验：返回错误说明（空串=通过）。集中在此以便主流程保持平坦。"""
    if not config.image_edit_api_key.strip():
        return "图片编辑功能未配置（IMAGE_EDIT_API_KEY 为空），无法改图。"
    if not images:
        return "本条消息里没有可用于编辑的图片。"

    total = len(images)
    hint = _INPUT_HINT.format(total=total)
    bad = [i for i in (base_image, *references) if not 1 <= i <= total]
    if bad:
        return f"图片序号越界 {bad}：{hint}"
    if len({base_image, *references}) > _MAX_INPUT_IMAGES:
        return f"一次最多用 {_MAX_INPUT_IMAGES} 张图（1 张原图 + 2 张参照）。"
    return _quota_block(uid, config)


def _order_images(
    images: list[ImageData], base_image: int, references: list[int]
) -> list[ImageData]:
    """图序固定为 [被修改的原图, *参照图]，与精修提示词"图一 = 原图"的约定一致。"""
    refs = [i for i in (int(x) for x in references) if i != base_image]
    return [images[base_image - 1], *(images[i - 1] for i in refs)]


async def _refine_instruction(
    config: AiChatConfig,
    *,
    user_request: str,
    image_count: int,
    base_index: int,
    references: list[int],
) -> str:
    """用隔离子 Agent 精修指令；任何失败返回空串，由调用方回退到用户原话。"""
    try:
        session = _session_id(current_scope.get())
        model = (
            get_session_model(session, config.ai_model) if session else config.ai_model
        )
        client = await get_client_for_model(config, model)
        agent = ImageEditAgent(
            client=client,
            tools=[],
            model=model,
            user_request=user_request,
            image_count=image_count,
            base_index=base_index,
            reference_indexes=references,
            tool_registry=TOOLS,
            usage_recorder=token_usage.record,
        )
        refined = (await agent.execute(fail_msg=_REFINE_FAIL_MARK)).strip()
    except Exception:  # noqa: BLE001  Agent 层已兜底，这里防构造阶段异常
        logger.warning("图片编辑指令精修异常，回退为用户原话", exc_info=True)
        return ""
    if not refined or refined.startswith(_REFINE_FAIL_MARK) or refined == _GENERIC_FAIL:
        return ""
    return refined


@register_tool(
    name="edit_image",
    description=(
        "当用户发来图片并要求**修改图片内容**时调用本工具：换装、换发型、改体型、"
        "换颜色/材质、增删画面元素、改画风等。\n"
        "参数用法（本条消息里的图片按出现顺序编号为 图一、图二…）：\n"
        "  · 「把这件衣服换成蓝色卫衣」→ instruction 照抄意图，base_image=1\n"
        "  · 「把图二的衣服换到图一身上」→ base_image=1, reference_images=[2]\n"
        "  · 「参照图二的体型改图一」→ base_image=1, reference_images=[2]\n\n"
        "不要调用的情况：\n"
        "1) 用户只是让你看/描述/识别图片内容——直接用你自身的看图能力回答，不要改图；\n"
        "2) 本条消息没有任何图片；\n"
        "3) 用户只是在讨论图片，并没有要求真的改。\n\n"
        "调用成功后图片由系统直接发给用户，你只需回一句简短确认，不要复述修改细节。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "instruction": {
                "type": "string",
                "description": (
                    "用户想怎么改，用自然语言把其意图完整转述"
                    "（不要自己发挥成画面细节清单，精修交给系统）。"
                ),
            },
            "base_image": {
                "type": "integer",
                "description": (
                    "被修改的原图序号（按本条消息中图片出现顺序，从 1 开始）。"
                    "单图场景省略即可（默认 1）。"
                ),
            },
            "reference_images": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "作为参照的图片序号数组，例如「把图二的衣服换到图一身上」传 [2]。"
                    "没有参照图就不要传。"
                ),
            },
        },
        "required": ["instruction"],
    },
)
async def edit_image_tool(
    instruction: str,
    base_image: int = 1,
    reference_images: list[int] | None = None,
) -> str:
    """AI 调用的图像编辑工具"""
    # 本轮已完成过一次：直接拒绝，避免模型重复调用把费用翻倍
    if current_edited_images.get() is not None:
        return "✅ 本轮已改过一次图，不必重复调用，直接给用户一句简短确认即可。"

    config = get_plugin_config(AiChatConfig)
    images = current_images.get() or []
    references = [int(i) for i in (reference_images or [])]

    blocked = _validate(
        images, base_image, references, config, _requester_uid(current_scope.get())
    )
    if blocked:
        return f"❌ {blocked}"

    # 指令精修（可关闭）：失败就退回主模型给的原话，保证功能可用
    final_instruction = instruction.strip()
    if config.image_edit_prompt_refine:
        refined = await _refine_instruction(
            config,
            user_request=final_instruction,
            image_count=len(images),
            base_index=base_image,
            references=references,
        )
        if refined:
            final_instruction = refined
        else:
            logger.warning("指令精修未产出有效结果，改用主模型原话")

    ordered = _order_images(images, base_image, references)
    sender = current_send_msg.get()
    if sender is not None:
        try:
            await sender("🎨 正在处理图片，大约需要 20 秒…")
        except Exception:  # noqa: BLE001  提示失败不能影响主流程
            logger.debug("图片编辑进度提示发送失败", exc_info=True)

    try:
        client = await get_image_edit_client(config)
        outcome = await client.edit(
            ordered, final_instruction, size=_target_size(ordered[0], config)
        )
    except ImageEditError as exc:
        logger.warning("图像编辑失败：%s", exc)
        return f"❌ 改图失败：{exc}"
    except Exception:
        logger.exception("图像编辑出现未预期异常")
        return "❌ 改图失败：内部错误，请稍后重试。"

    # 产出交给 handler 发图（工具作用域没有 matcher）
    current_edited_images.set(outcome.images)
    # 图像编辑按图计费：usage 里既无金额也无 token，不能混进 token 用量报表
    logger.info(
        "图片编辑完成 model=%s 输入图=%d 产出=%d request_id=%s usage=%s",
        config.image_edit_model,
        len(ordered),
        len(outcome.images),
        outcome.request_id or "-",
        outcome.usage or {},
    )
    return "✅ 已完成图片修改，成品由系统直接发给用户，你只需用一句话回应。"
