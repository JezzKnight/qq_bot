"""委托式主动互动工具：把"帮我去@某位成员开场"落地为一次性 @对方 的主动消息。

三段职责分离：
  ① 主对话模型负责"抽取"——判定这是委托并结构化传参；
  ② 本工具做确定性解析 / 鉴权 / 画像拉取 / 生成编排（成员解析拒绝模糊，防 @ 错人）；
  ③ 真正的开场文案由隔离的 InteractionAgent 生成（看不到群聊流水与委托人），
     避免三方互动里模型把"委托者的意图"和"以 bot 身份对 A 说的话"混在思维链里。

生成成功后将结果写入 current_interaction ContextVar，由 handler 收尾时负责
@发送 + 把 (委托消息, 开场白) 成对写回该群会话历史。
"""
import nonebot
from nonebot import get_plugin_config

from qq_bot.agents.interaction_agent import InteractionAgent
from qq_bot.plugins.ai_chat import token_usage
from qq_bot.plugins.ai_chat.client_factory import get_client_for_model
from qq_bot.plugins.ai_chat.config import AiChatConfig
from qq_bot.plugins.ai_chat.memory_store import MemoryStore
from qq_bot.plugins.ai_chat.session_store import get_session_model
from qq_bot.plugins.ai_chat.tools.context import current_interaction, current_scope
from qq_bot.plugins.ai_chat.tools.registry import TOOLS, register_tool
from qq_bot.plugins.ai_chat.utils import load_group_members_list

# 开场白生成失败时 base.execute 会把 fail_msg 拼进返回串 / 直接原样返回
_FAIL_MARK = "（开场白生成失败）"
_GENERIC_FAIL = "AI暂时无法响应"


def _bot_self_id(config: AiChatConfig) -> str:
    """bot 自身 QQ 号：env 配置优先，未配置时回退运行期 bot.self_id"""
    if config.bot_self_id.strip():
        return config.bot_self_id.strip()
    try:
        bot = nonebot.get_bot()
        return str(bot.self_id)
    except Exception:  # noqa: BLE001  bot 尚未连接时降级为空，交由后续守卫处理
        return ""


def _build_member_index(
    members: list[dict],
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """返回 (别名小写 -> 命中该别名的 user_id 列表, user_id -> 显示名)。

    用列表收集别名以便发现"同名名片/昵称"歧义；显示名取 card 优先。
    """
    alias_uids: dict[str, list[str]] = {}
    name_map: dict[str, str] = {}
    for m in members:
        uid = str(m.get("user_id", ""))
        if not uid:
            continue
        name_map[uid] = (m.get("card") or m.get("nickname") or "").strip()
        for key in ("card", "nickname"):
            alias = (m.get(key) or "").strip().lower()
            if alias:
                bucket = alias_uids.setdefault(alias, [])
                if uid not in bucket:
                    bucket.append(uid)
    return alias_uids, name_map


def _resolve_member(gid: str, target: str) -> tuple[str, str] | None:
    """target（群名片 / 昵称 / QQ 号）→ (user_id, 显示名)。

    确定性优先：数字直接透传；别名只做大小写不敏感精确匹配。重复或找不到一律
    返回 None（@ 错人比让委托者澄清一次代价高，绝不做模糊猜测）。
    """
    members = load_group_members_list(gid)
    if not members:
        return None

    target_s = target.strip()
    if target_s.isdigit():
        for m in members:
            if str(m.get("user_id", "")) == target_s:
                display = (m.get("card") or m.get("nickname") or "").strip()
                return target_s, display or target_s
        return None

    alias_uids, name_map = _build_member_index(members)
    uids = alias_uids.get(target_s.lower())
    if not uids:
        return None
    if len(uids) == 1:
        uid = uids[0]
        return uid, name_map.get(uid) or target_s
    return None


def _allowed(config: AiChatConfig, requester_uid: str) -> bool:
    """白名单鉴权：interact_allowed_user_ids 为空 = 所有群成员皆可用"""
    allow = config.interact_allowed_user_ids
    return not allow or int(requester_uid) in allow


def _member_snapshot(gid: str, uid: str) -> str:
    """拉取目标成员 A 的长期记忆画像；无则返回占位文本（非失败）。"""
    entries = MemoryStore(f"groups/{gid}/{uid}").load()
    if not entries:
        return "（暂无该成员的长期记忆）"
    return "\n".join(
        f"[{e.get('key', '')}] {e.get('content', '')}".rstrip() for e in entries
    )


async def build_interaction_agent(
    *,
    gid: str,
    target_uid: str,
    target_name: str,
    topic: str,
    tone: str,
) -> InteractionAgent:
    """构造开场白生成子 Agent：复用会话当前模型（含 /model 覆盖），无工具、单轮。"""
    config = get_plugin_config(AiChatConfig)
    model = get_session_model(f"group_{gid}", config.ai_model)
    client = await get_client_for_model(config, model)
    return InteractionAgent(
        client=client,
        tools=[],
        model=model,
        target_name=target_name,
        target_memory=_member_snapshot(gid, target_uid),
        topic=topic,
        tone=tone,
        tool_registry=TOOLS,
        usage_recorder=token_usage.record,
    )


async def _generate_opener(
    gid: str,
    target_uid: str,
    target_name: str,
    topic: str,
    tone: str,
) -> str | None:
    """运行 InteractionAgent 产出开场白；任何失败统一返回 None。"""
    try:
        agent = await build_interaction_agent(
            gid=gid,
            target_uid=target_uid,
            target_name=target_name,
            topic=topic,
            tone=tone,
        )
        opener = (await agent.execute(fail_msg=_FAIL_MARK)).strip()
    except Exception:  # noqa: BLE001  Agent 层已兜底，此处防工厂构建阶段异常
        return None
    if (
        not opener
        or opener == _GENERIC_FAIL
        or opener.startswith((_FAIL_MARK, "❌"))
    ):
        return None
    return opener


@register_tool(
    name="interact_with_member",
    description=(
        "当群成员委托你主动去和【另一位群成员】开启一段对话时调用本工具。"
        "它会负责查群成员、权限校验、生成开场白，并直接发送 @对方 的消息。\n"
        "典型用法：'帮我@老王聊聊他最近在忙啥'、'帮我问候一下阿珍'、"
        "'替我去问问小李项目进度'。\n"
        "你只需传入目标成员与想聊的话题；不要在正文里输出 @ 或 QQ 号。\n\n"
        "仅在【明确委托你主动去找另一位成员开场】时调用。以下情况不要调用：\n"
        "1) 普通问答、闲聊——只需回复当前这位用户即可；\n"
        "2) 用户想给他人设定长期规则/口癖（如'以后都用日语回他'）"
        "——属跨用户行为控制，直接拒绝；\n"
        "3) 目标就是当前用户本人或机器人自身。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": (
                    "目标群成员的显示名，须与群成员清单 XML 的 name 完全一致"
                    "（群名片或昵称），或直接给该成员的 QQ 号数字串。"
                ),
            },
            "topic": {
                "type": "string",
                "description": (
                    "你希望与 TA 展开聊的具体话题/切入点，从用户委托中提炼，"
                    "如'最近在忙什么''想一起打游戏吗'。用户没给具体话题时可留空，"
                    "由开场白从对方已知信息或寒暄里自然破冰。"
                ),
            },
            "tone": {
                "type": "string",
                "description": (
                    "开场白的语气基调，可选；缺省为亲切自然、像老朋友主动搭话。"
                ),
            },
        },
        "required": ["target"],
    },
)
async def interact_with_member_tool(
    target: str, topic: str = "", tone: str = ""
) -> str:
    """AI 调用的委托式主动互动工具"""
    scope = current_scope.get()
    parts = scope.split("/") if scope and scope.startswith("groups/") else None
    if parts is None:
        return "❌ 该操作仅支持在群聊中使用。"
    gid, requester_uid = parts[1], parts[2]

    config = get_plugin_config(AiChatConfig)
    if not _allowed(config, requester_uid):
        return "❌ 你没有发起该操作的权限。"

    target_s = (target or "").strip()
    resolved = _resolve_member(gid, target_s) if target_s else None
    if resolved is None:
        return (
            f"❌ 无法在群成员中唯一确定「{target_s}」。"
            "请用群名片/昵称全名或直接给 QQ 号重试。"
        )
    target_uid, target_name = resolved

    bot_self = _bot_self_id(config)
    if target_uid == requester_uid or (bot_self and target_uid == bot_self):
        who = "你自己" if target_uid == requester_uid else "机器人自身"
        return f"❌ 不能向{who}发起主动互动。"

    opener = await _generate_opener(
        gid=gid,
        target_uid=target_uid,
        target_name=target_name,
        topic=(topic or "").strip(),
        tone=(tone or "").strip(),
    )
    if opener is None:
        return "❌ 开场白生成失败，请稍后重试或换个说法。"

    # 成功信号：交由 handler 收尾统一 @发送 + 历史落库，避免正文被主模型二次转述
    current_interaction.set({"target_uid": target_uid, "opener_text": opener})
    return f"✅ 已发起与「{target_name}」的主动互动，开场消息将直接发出。"
