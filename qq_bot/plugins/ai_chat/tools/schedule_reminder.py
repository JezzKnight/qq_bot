from datetime import datetime

from qq_bot.plugins.ai_chat.tools.registry import register_tool
from qq_bot.plugins.ai_chat.tools.context import current_scope

from ...scheduled_tasks.reminder_manager import schedule_reminder


async def _parse_user_intended_time(text:str) -> str | None:
    """将用户的口语时间表达解析为 ISO 8601

    这是整个功能最"脏"的部分——NLU 时间解析。
    策略：优先让 AI 在调用 tool 前自己算好，这里做二次校验。

    输入示例：
      "今晚12点"  → AI 应计算出 "2026-06-30T00:00:00"
      "明天下午3点" → AI 应计算出 "2026-06-30T15:00:00"
      "3小时后"    → AI 应计算出具体时间

    如果 AI 传了不可解析的格式，这里返回 None 并报错。
    """
    try:
        dt = datetime.fromisoformat(text)
        if dt <= datetime.now():
            return None
        return dt.isoformat()
    except (ValueError, TypeError):
        return None


@register_tool(
    name="schedule_reminder",
    description=(
        "为用户设置一次性定时提醒。"
        "当用户说'X时间提醒我Y'时，调用此工具。"
        "remind_at 必须是 ISO 8601 格式的精确时间（如 2026-06-30T00:00:00），"
        "你必须根据当前时间和用户的表述自行计算出精确时间。"
        "message 是你将要推送的提醒内容，应友好、完整。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "remind_at": {
                "type": "string",
                "description": (
                    "提醒的精确时间，ISO 8601 格式。"
                    "当前时间: " + datetime.now().isoformat() + "。"
                    "请根据用户表述计算：'今晚12点'→当天 00:00:00，注意日期变更。"
                ),
            },
            "message": {
                "type": "string",
                "description": "提醒推送的完整内容，如'该睡觉了！已经凌晨了，早点休息吧 🌙'",
            },
        },
        "required": ["remind_at", "message"],
    },
)
async def schedule_reminder_tool(remind_at: str, message: str) -> str:
    """AI调用的提醒创建工具"""
    # 直接从current_scope中获取数据
    scope = current_scope.get()
    if scope is None:
        return "❌ 无法确定当前会话上下文，请稍后重试。"
    
    parts = scope.split("/")
    # 群聊与私聊的分开处理
    if parts[0] == "groups":
        target_type = "group"
        target_id = parts[1]
        creator_user_id = parts[2]
    else:
        target_type = "private"
        target_id = parts[1]
        creator_user_id = parts[1]
    # 校验时间
    parsed_time = await _parse_user_intended_time(remind_at)
    if parsed_time is None:
        return f"❌ 时间格式错误或已过期: {remind_at}。请使用 ISO 8601 格式（如 2026-06-30T00:00:00）。"
    # 创建提醒任务
    try:
        reminder = await schedule_reminder(
            remind_at=remind_at,
            message=message,
            target_type=target_type,
            target_id=target_id,
            creator_user_id=creator_user_id
        )
        msg = (
            f"✅ 提醒已设置！\n"
            f"⏰ 时间: {reminder.remind_at}\n"
            f"📝 内容: {reminder.message}\n"
            f"🔑 ID: {reminder.job_id}")
        print(msg)
        return msg
    except Exception as e:
        return f"❌ 提醒创建失败: {e}"
    
