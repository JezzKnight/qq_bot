# ruff: noqa: E501   # 工具描述含中文长句，行宽超过 88 属有意为之
"""成员长期记忆查询工具：按需读取指定成员的个人长期记忆。

动态注入只覆盖群公共记忆 + 当前发言人 + 本条消息提及的成员；
本工具供模型在需要了解其他成员时按 target_uid 主动查询。
"""
from qq_bot.plugins.ai_chat.memory_store import MemoryStore
from qq_bot.plugins.ai_chat.utils import load_group_members_list

from .context import current_scope
from .registry import register_tool


def _member_display_name(gid: str, uid: str) -> str:
    """从 members.json 解析成员显示名（card 优先，nickname 兜底）；未知返回空串。"""
    members = load_group_members_list(gid) or []
    for m in members:
        if str(m.get("user_id", "")) == uid:
            return (m.get("card") or m.get("nickname") or "").strip()
    return ""


@register_tool(
    name="recall_memory",
    description=(
        "读取指定成员的长期记忆。\n\n"
        "## 何时调用\n"
        "动态注入只覆盖：群公共记忆、当前发言人、本条消息按名字匹配到的成员。"
        "当你需要了解某个【其他】成员（既非当前发言人、也未被本条消息提及）的背景，"
        "且这份信息可能影响回答时，调用本工具查询该成员的长期记忆。\n\n"
        "## 参数\n"
        "target_uid：目标成员的 user_id，"
        "从对话中 <user identity> 标签的 id 属性或群成员列表 XML 中获取。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "target_uid": {
                "type": "string",
                "description": "目标成员的 user_id，从 <user identity> 标签 id 属性或群成员列表获取"
            }
        },
        "required": ["target_uid"]
    },
)
async def recall_memory(target_uid: str) -> str:
    """读取指定成员的个人长期记忆"""
    raw_scope = current_scope.get()
    if not raw_scope.startswith("groups/"):
        return "该工具仅群聊可用"
    gid = raw_scope.split("/")[1]
    entries = MemoryStore(f"groups/{gid}/{target_uid}").load()
    if not entries:
        return f"成员 {target_uid} 暂无长期记忆"
    name = _member_display_name(gid, target_uid)
    lines = [f'## <user id="{target_uid}" name="{name}"/> 的个人记忆']
    lines.extend(
        f"[{e.get('key', '')}] {e.get('content', '')}".rstrip() for e in entries
    )
    return "\n".join(lines)
