"""查看当前会话的提醒列表 —— 用户命令 /reminders"""
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent
from nonebot.matcher import Matcher
from nonebot.rule import to_me

from ...scheduled_tasks.reminder_manager import list_by_target

reminders_cmd = on_command(
    "reminders",
    rule=to_me(),
    aliases={"提醒列表", "我的提醒", "定时任务列表"},
    block=True,
    force_whitespace=True,
)


@reminders_cmd.handle()
async def handle_list_reminders(event: MessageEvent, matcher: Matcher):
    """列出当前会话中所有 pending 状态的提醒"""
    if isinstance(event, GroupMessageEvent):
        target_type, target_id = "group", str(event.group_id)
    else:
        target_type, target_id = "private", str(event.user_id)

    try:
        items = await list_by_target(target_type, target_id, status="pending")
    except Exception:
        await matcher.finish("❌ 定时任务系统暂不可用，请稍后重试。")

    if not items:
        await matcher.finish("📭 当前没有待执行的提醒或定时任务。")

    lines = [f"📋 当前共有 {len(items)} 个待执行任务：\n"]
    for r in items:
        tag = "🤖" if r.task_type == "agent_task" else "⏰"
        lines.append(
            f"{tag} [{r.remind_at}] {r.message[:40]}{'...' if len(r.message) > 40 else ''}\n"
            f"   ID: {r.job_id}"
        )
        if r.task_type == "agent_task":
            lines.append("   (智能任务，到时间自动执行)")

    await matcher.finish("\n".join(lines))
