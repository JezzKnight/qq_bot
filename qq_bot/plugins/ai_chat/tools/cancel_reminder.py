"""取消提醒的 AI 工具

AI 在对话中根据用户意图调用。只允许取消当前会话下的提醒。
"""
from .registry import register_tool
from .context import current_scope
from ...scheduled_tasks.reminder_manager import cancel_reminder


def _scope_to_parts() -> tuple[str, str] | None:
    """从 current_scope 提取 target_type 和 target_id"""
    scope = current_scope.get()
    if scope is None:
        return None
    parts = scope.split("/")
    if parts[0] == "groups":
        return "group", parts[1]
    return "private", parts[1]


@register_tool(
    name="cancel_reminder",
    description=(
        "取消用户之前设置的定时提醒或智能任务。"
        "当用户说'取消提醒''取消定时任务''不用提醒了'时调用。"
        "只能取消当前会话中创建的提醒。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "要取消的提醒 ID，由 schedule_reminder 创建时返回。",
            },
        },
        "required": ["job_id"],
    },
)
async def cancel_reminder_tool(job_id: str) -> str:
    """取消指定提醒，校验归属权限"""
    scope_info = _scope_to_parts()
    if scope_info is None:
        return "❌ 无法确定当前会话上下文。"

    from ...scheduled_tasks.reminder_manager import _repo

    if _repo is None:
        return "❌ 提醒系统未初始化。"

    reminder = await _repo.get_by_job_id(job_id)
    if reminder is None:
        return f"❌ 未找到提醒 {job_id}，可能已过期或已取消。"

    target_type, target_id = scope_info
    if reminder.target_type != target_type or reminder.target_id != target_id:
        return "❌ 无权取消该提醒，不属于当前会话。"

    ok = await cancel_reminder(job_id)
    if ok:
        return f"✅ 提醒已取消: {reminder.message[:30]}..."
    return f"❌ 取消失败，提醒 {job_id} 可能已过期。"
