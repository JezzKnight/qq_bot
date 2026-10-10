"""本地 ComfyUI 生图：/comfyui + 图片 → 原样触发现成 i2i 工作流（demo 版）。

交互：图片和 /comfyui 同一条消息发出（群聊需 @bot）。不解析提示词，
工作流只改写两处：LoadImage 节点的输入图、seed 随机化（API 导出的
seed 是固定值，不随机化则同一张图永远产出同一结果）。

ComfyUI 侧流程：POST /upload/image 传图 → 改写工作流 → POST /prompt 排队
→ 轮询 /history/{prompt_id} → GET /view 下载产物 → 发回群聊。
"""

import asyncio
import json
import random
import time

import httpx
from anyio import Path as AsyncPath
from nonebot import get_plugin_config, on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.matcher import Matcher
from nonebot.rule import to_me

from qq_bot.plugins.ai_chat.config import AiChatConfig

# 群聊需 @bot 触发；指令不带参数，不开 force_whitespace
comfyui_cmd = on_command("comfyui", rule=to_me(), block=True)

# 工作流里的种子输入名（RandomNoise.noise_seed / SeedVR2*.seed），每次触发随机化
_SEED_INPUT_NAMES = {"seed", "noise_seed"}
# 随机 seed 的取值上限：SeedVR2 等自定义节点把 seed 上限声明为 2^32-1，
# 掷出的值必须压在所有已知上限之下（2^48 范围曾触发校验 value_bigger_than_max）
_MAX_SEED = 2**31 - 1
# 轮询 /history 的间隔（秒）
_POLL_INTERVAL = 2.0


def _api(config: AiChatConfig, path: str) -> str:
    return config.comfyui_api_base.rstrip("/") + path


def _randomize_seeds(workflow: dict) -> None:
    """随机化工作流中所有 seed 类整型输入（原地修改）"""
    for node in workflow.values():
        inputs = node.get("inputs", {})
        for name in _SEED_INPUT_NAMES:
            if isinstance(inputs.get(name), int):
                inputs[name] = random.randrange(_MAX_SEED + 1)


def _input_image_ref(upload: dict) -> str:
    """把 /upload/image 的响应转成 LoadImage 输入需要的路径格式"""
    subfolder = upload.get("subfolder") or ""
    name = upload.get("name", "")
    return f"{subfolder}/{name}" if subfolder else name


def _set_input_image(workflow: dict, ref: str, node_id: str) -> None:
    """把用户图喂进工作流的 LoadImage 节点（原地修改）"""
    workflow[node_id]["inputs"]["image"] = ref


def _collect_output_images(history_entry: dict) -> list[tuple[str, str, str]]:
    """从 /history 条目提取产物图列表 (filename, subfolder, type)"""
    images: list[tuple[str, str, str]] = []
    for node_output in history_entry.get("outputs", {}).values():
        images.extend(
            (
                img.get("filename", ""),
                img.get("subfolder", ""),
                img.get("type", "output"),
            )
            for img in node_output.get("images", [])
        )
    return images


def _extract_image(message: Message) -> MessageSegment | None:
    """取消息里的第一张图片段，没有则 None"""
    for seg in message:
        if seg.type == "image":
            return seg
    return None


async def _upload_image(
    client: httpx.AsyncClient, config: AiChatConfig, img_bytes: bytes, filename: str
) -> dict:
    resp = await client.post(
        _api(config, "/upload/image"),
        data={"overwrite": "true"},
        files={"image": (filename, img_bytes, "image/png")},
    )
    resp.raise_for_status()
    return resp.json()


async def _queue_workflow(
    client: httpx.AsyncClient, config: AiChatConfig, workflow: dict
) -> str:
    resp = await client.post(
        _api(config, "/prompt"), json={"prompt": workflow, "client_id": "qq_bot"}
    )
    if not resp.is_success:
        # 节点校验失败等，ComfyUI 返回 400 + error 详情
        raise RuntimeError(resp.text[:200])
    return resp.json()["prompt_id"]


async def _wait_for_result(
    client: httpx.AsyncClient, config: AiChatConfig, prompt_id: str
) -> list[tuple[str, str, str]] | None:
    """轮询 /history 直到跑完；完成返回产物列表，超时/失败返回 None"""
    deadline = time.monotonic() + config.comfyui_timeout
    while time.monotonic() < deadline:
        resp = await client.get(_api(config, f"/history/{prompt_id}"))
        entry = resp.json().get(prompt_id)
        if entry:
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                return None
            if status.get("completed"):
                return _collect_output_images(entry)
        await asyncio.sleep(_POLL_INTERVAL)
    return None


async def _download_output(
    client: httpx.AsyncClient,
    config: AiChatConfig,
    filename: str,
    subfolder: str,
    file_type: str,
) -> bytes | None:
    resp = await client.get(
        _api(config, "/view"),
        params={"filename": filename, "subfolder": subfolder, "type": file_type},
    )
    return resp.content if resp.is_success else None


@comfyui_cmd.handle()
async def handle_comfyui(event: MessageEvent, matcher: Matcher) -> None:
    config = get_plugin_config(AiChatConfig)
    if not config.comfyui_workflow:
        await matcher.finish("未配置生图工作流（COMFYUI_WORKFLOW）")
    seg = _extract_image(event.message)
    if seg is None:
        await matcher.finish("请把图片和 /comfyui 一起发")
    url = seg.data.get("url")
    if not url:
        await matcher.finish("没能拿到图片地址，换张图再试")

    await matcher.send("🐋 收到，正在作画…")
    try:
        # 本地服务：关掉环境代理读取，避免 127.0.0.1 被系统代理劫持
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0), trust_env=False
        ) as client:
            img_resp = await client.get(url)
            if not img_resp.is_success:
                await matcher.finish("图片下载失败，再发一次试试")
            upload = await _upload_image(
                client, config, img_resp.content, f"qq_{event.user_id}.png"
            )
            # 工作流模板保持原样触发，只喂入用户图 + 随机化种子
            wf_json = await AsyncPath(config.comfyui_workflow).read_text("utf-8")
            workflow = json.loads(wf_json)
            _set_input_image(
                workflow, _input_image_ref(upload), config.comfyui_upload_node
            )
            _randomize_seeds(workflow)
            prompt_id = await _queue_workflow(client, config, workflow)
            images = await _wait_for_result(client, config, prompt_id)
            if not images:
                await matcher.finish("生成失败或超时了，稍后再试")
            for filename, subfolder, file_type in images:
                data = await _download_output(
                    client, config, filename, subfolder, file_type
                )
                if data:
                    await matcher.send(MessageSegment.image(data))
    except httpx.ConnectError:
        await matcher.finish("连不上 ComfyUI，服务开了吗？")
    except RuntimeError as e:
        await matcher.finish(f"工作流被 ComfyUI 拒绝：{e}")
    return await matcher.finish()
