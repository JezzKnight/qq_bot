"""按日期查询对话历史的 AI 工具

供定时任务 Agent 和正常对话使用：
  - "帮我回顾一下昨天群里聊了什么"
  - "总结上周三的讨论内容"
  - 定时任务：每天 8 点自动总结前一天的群聊
"""
from datetime import datetime, timedelta

from .registry import register_tool
from .context import current_scope
from ..memory_writing import get_memory
from ..config import AiChatConfig
from nonebot import get_plugin_config


def _resolve_date(date_input: str) -> str | None:
    """将 AI 传入的日期字符串解析为标准 ISO 日期 "2026-07-03"

    支持的格式：
      - "2026-07-03"        → 直接返回
      - "today" / "今天"     → 今天
      - "yesterday" / "昨天" → 昨天
      - "3 days ago"         → 3 天前
    """
    date_input = date_input.strip()

    # 已经是 ISO 格式
    try:
        datetime.strptime(date_input, "%Y-%m-%d")
        return date_input
    except ValueError:
        pass

    now = datetime.now()
    mapping = {
        "today": now,
        "今天": now,
        "yesterday": now - timedelta(days=1),
        "昨天": now - timedelta(days=1),
    }
    if date_input in mapping:
        return mapping[date_input].strftime("%Y-%m-%d")

    # 尝试 "N days ago"
    for prefix in ("days ago", "天前"):
        if prefix in date_input:
            try:
                n = int(date_input.replace(prefix, "").strip())
                return (now - timedelta(days=n)).strftime("%Y-%m-%d")
            except ValueError:
                pass

    return None


def _format_messages(rows: list[dict], date_str: str) -> str:
    """将数据库行格式化为 AI 易读的文本"""
    if not rows:
        return f"📭 {date_str} 没有对话记录。"

    lines = [f"📅 {date_str} 对话记录（共 {len(rows)} 条）：\n"]
    for r in rows:
        time_part = r.get("created_at", "")[-8:]  # 截取 HH:MM:SS
        # 只保留前 5 位 HH:MM
        time_part = time_part[:5] if len(time_part) >= 5 else time_part
        name = r.get("sender_name", "")
        role = r["role"]
        content = r.get("content") or ""

        # 截断过长内容，避免上下文爆炸
        if len(content) > 500:
            content = content[:500] + "..."

        if role == "user":
            label = name if name else "用户"
            lines.append(f"[{time_part}] {label}: {content}")
        elif role == "assistant":
            lines.append(f"[{time_part}] assistant: {content}")
        elif role == "tool":
            lines.append(f"[{time_part}] [工具返回]: {content}")
        elif role == "system":
            continue  # system prompt 不展示

    return "\n".join(lines)


@register_tool(
    name="query_chat_history",
    description=(
        "查询指定日期的群聊或私聊对话记录。\n\n"
        "使用场景：\n"
        "- 用户要求回顾某天的聊天内容（'昨天大家聊了什么'）\n"
        "- 定时任务需要读取历史对话（每日总结、上下文回顾）\n"
        "- 需要了解过去某天的讨论话题\n\n"
        "date 支持：'2026-07-03'、'today'、'yesterday'、'昨天'、'3 days ago'"
    ),
    parameters={
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": (
                    "查询日期。支持格式：\n"
                    "- 绝对日期: '2026-07-03'\n"
                    "- 相对日期: 'today', 'yesterday', '昨天', '3 days ago'\n"
                    "参考当前时间: " + datetime.now().strftime("%Y-%m-%d %H:%M")
                ),
            },
            "limit": {
                "type": "integer",
                "description": "最多返回多少条消息，默认 200。群聊活跃时适当增大。",
            },
        },
        "required": ["date"],
    },
)
async def query_chat_history(date: str, limit: int = 200) -> str:
    """按日期查询当前会话的对话记录"""
    # 1. 解析日期
    date_str = _resolve_date(date)
    if date_str is None:
        return f"❌ 无法解析日期: '{date}'。请使用 ISO 格式如 '2026-07-03'。"

    # 2. 从上下文获取当前会话 ID
    scope = current_scope.get()
    if scope is None:
        return "❌ 无法确定当前会话上下文。"

    parts = scope.split("/")
    if parts[0] == "groups":
        session_id = f"group_{parts[1]}"
    else:
        session_id = f"user_{parts[1]}"

    # 3. 获取 MemoryManager 并查询
    try:
        config = get_plugin_config(AiChatConfig)
        memory = await get_memory(config)
        rows = await memory.get_history_by_date(
            session_id=session_id, date_str=date_str, limit=limit,
        )
    except Exception as e:
        return f"❌ 查询失败: {e}"

    # 4. 格式化返回
    return _format_messages(rows, date_str)
