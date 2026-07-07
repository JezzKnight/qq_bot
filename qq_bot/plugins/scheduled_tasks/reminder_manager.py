import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Awaitable

from nonebot import get_bot

from .reminder_repo import Reminder, ReminderRepository
from nonebot.adapters.onebot.v11 import MessageSegment
from .scheduler import SchedulerGateway


# ── 全局单例 ──
_repo: ReminderRepository | None = None
_gateway: SchedulerGateway | None = None
_agent_factory: Callable[[str], Awaitable] | None = None


def init(
    db_dir: Path,
    gateway: SchedulerGateway,
    agent_factory: Callable[[str], Awaitable] | None = None,
) -> ReminderRepository:
    """插件启动时调用一次，初始化存储和调度器引用"""
    global _repo, _gateway, _agent_factory
    _repo = ReminderRepository(db_dir / "reminders.db")
    _gateway = gateway
    _agent_factory = agent_factory
    return _repo


async def create_reminder(
    remind_at: str,
    message: str,
    target_type: str,
    target_id: str,
    creator_user_id: str,
    task_type: str,
) -> Reminder:
    """创建提醒 → 写入数据库 → 注册 APScheduler"""
    if _repo is None or _gateway is None:
        raise RuntimeError("ReminderManager 未初始化")

    job_id = f"reminder_{uuid.uuid4().hex[:12]}"

    reminder = Reminder(
        remind_at=remind_at,
        message=message,
        target_type=target_type,
        target_id=target_id,
        creator_user_id=creator_user_id,
        task_type=task_type,
        job_id=job_id,
        status="pending",
    )
    await _repo.save(reminder)

    trigger_time = datetime.fromisoformat(remind_at)
    _gateway.add_reminder(
        job_id=job_id,
        run_at=trigger_time,
        callback=_fire_reminder,
    )

    return reminder


async def cancel_reminder(job_id: str) -> bool:
    """取消一条未触发的提醒"""
    if _repo is None or _gateway is None:
        raise RuntimeError("ReminderManager 未初始化")

    _gateway.remove_reminder(job_id)
    return await _repo.cancel(job_id)


async def list_by_target(
    target_type: str, target_id: str, status: str | None = "pending",
) -> list[Reminder]:
    """查询指定目标的提醒列表，默认只返回 pending 状态"""
    if _repo is None:
        raise RuntimeError("ReminderManager 未初始化")
    return await _repo.get_by_target(target_type, target_id, status)


async def _fire_reminder(job_id: str):
    """APScheduler 回调，根据 task_type 分支处理 reminder / agent_task"""
    if _repo is None:
        return

    reminder = await _repo.get_by_job_id(job_id)
    if reminder is None or reminder.status != "pending":
        return

    try:
        if reminder.task_type == "agent_task":
            if _agent_factory is None:
                raise RuntimeError("agent_factory 未注入")
            agent = await _agent_factory(reminder.message)
            result_text = await agent.execute(
                fail_msg="❌ 定时任务执行失败，请稍后重试。"
            )
            push_content = f"⏰ 定时任务\n\n{result_text}"
        else:
            push_content = f"⏰ 提醒：{reminder.message}"

        bot = get_bot()
        if reminder.target_type == "group":
            # 群聊提醒添加艾特功能
            await bot.send_group_msg(
                group_id=int(reminder.target_id), message=f"{MessageSegment.at(reminder.creator_user_id)}\n{push_content}",
            )
        elif reminder.target_type == "private":
            await bot.send_private_msg(
                user_id=int(reminder.target_id), message=push_content,
            )

        await _repo.mark_fired(job_id)
        print(f"[INFO] 已触发: job_id={job_id}")

    except Exception:
        print(f"[WARN] 触发失败: job_id={job_id}")
