import uuid
import logging
from datetime import datetime
from pathlib import Path

from nonebot import get_bot
from nonebot.adapters.onebot.v11 import Bot

from .reminder_repo import Reminder, ReminderRepository

# ── 全局单例 ──
_reminder_repo: ReminderRepository | None = None
_reminder_scheduler = None  # APScheduler 实例，由插件入口注入

def init_reminder_manager(db_dir:Path, schedule):
    """插件启动的时候嗲用一次，初始化储存和调度器引用"""
    global _reminder_repo, _reminder_scheduler
    _reminder_repo = ReminderRepository(db_dir / "reminders.db")
    _reminder_scheduler = schedule


async def schedule_reminder(
        remind_at: str,
        message: str,
        target_type: str,
        target_id: str,
        creator_user_id: str,
    ) ->  Reminder:
    """创建提醒->写入数据库->注册 APScheduler"""
    if _reminder_repo is None or _reminder_scheduler is None:
        raise RuntimeError("RenminderManager 未初始化")
    
    job_id = f"reminder_{uuid.uuid4().hex[:12]}" #?

    reminder = Reminder(
        remind_at=remind_at,
        message=message,
        target_type=target_type,
        target_id=target_id,
        creator_user_id=creator_user_id,
        job_id=job_id,
        status="pending",
    )
    await _reminder_repo.save(reminder)

    trigger_time = datetime.fromisoformat(remind_at) #?
    _reminder_scheduler.add_job(
        func = _fire_reminder,
        trigger="data",
        run_date=trigger_time,
        id=job_id,
        args=[job_id],
        misfire_grace_time=60
    ) #?

    return reminder


async def cancel_reminder(job_id) -> bool:
    """取消一条未触发的提醒"""
    if _reminder_repo is None or _reminder_scheduler is None:
        raise RuntimeError("RenminderManager 未初始化")
    
    if _reminder_scheduler.get_job(job_id):
        _reminder_scheduler.remove_job(job_id) #?

    updated = await _reminder_repo.cancel(job_id)
    if updated:
        print(f"[INFO] 已取消：id={job_id}")
    return updated


async def _fire_reminder(job_id:str):
    """提醒触发时的回调 —— 由 APScheduler 调用

    在 add_job 时通过 args=[job_id] 传入，回调时查库获取详情。
    """
    if _reminder_repo is None:
        return

    # 1. 从数据库查询提醒详情
    reminder = await _reminder_repo.get_by_job_id(job_id)
    if reminder is None:
        print(f"[WARN] job_id={job_id} 在数据库中不存在，跳过")
        return

    if reminder.status != "pending":
        print(f"[INFO] job_id={job_id} 状态={reminder.status}，跳过")
        return

    # 2. 获取 bot 实例并推送消息
    try:
        bot = get_bot()

        if reminder.target_type == "group":
            await bot.send_group_msg(
                group_id=int(reminder.target_id),
                message=f"⏰ 提醒\n\n{reminder.message}",
            )
        elif reminder.target_type == "private":
            await bot.send_private_msg(
                user_id=int(reminder.target_id),
                message=f"⏰ 提醒\n\n{reminder.message}",
            )

        # 3. 标记为已完成
        await _reminder_repo.mark_fired(job_id)
        print(f"[提醒] 已触发并推送: job_id={job_id}")

    except Exception:
        print(f"[WARN] 推送失败: job_id={job_id}")
        # 不标记为 fired，下次启动时可以重试或人工处理