"""定时任务插件入口"""
from nonebot import get_driver, require
from nonebot.plugin import PluginMetadata
from nonebot_plugin_localstore import get_plugin_data_dir

from .scheduler import SchedulerGateway
from .reminder_manager import init as init_manager, _fire_reminder

# 从 AI 工具层导入工厂函数
from qq_bot.plugins.ai_chat.tools.schedule_reminder import build_scheduled_agent

__plugin_meta__ = PluginMetadata(
    name="定时任务",
    description="提醒 + 智能定时任务调度",
    usage="由 AI 在对话中通过 schedule_reminder 工具自动创建",
)

_driver = get_driver()
# 获取APScheduler实例
_scheduler = require("nonebot_plugin_apscheduler").scheduler

# 持有 repo 引用，用于启动恢复和关闭清理
_repo = None


@_driver.on_startup
async def _startup():
    global _repo

    data_dir = get_plugin_data_dir()
    gateway = SchedulerGateway(_scheduler)

    # 注入：把 agent 工厂函数传进 reminder_manager，拿回 repo 实例
    _repo = init_manager(
        db_dir=data_dir,
        gateway=gateway,
        agent_factory=build_scheduled_agent,
    )

    await _repo.init()

    # 恢复 pending 任务
    from datetime import datetime
    pending = await _repo.get_all_pending()
    now = datetime.now()
    restored = 0
    for r in pending:
        trigger_time = datetime.fromisoformat(r.remind_at)
        if trigger_time <= now:
            # 已过期：立即补发
            await _fire_reminder(r.job_id)
        else:
            # 未来任务：重新注册到调度器
            gateway.add_reminder(
                job_id=r.job_id,
                run_at=trigger_time,
                callback=_fire_reminder,
            )
            restored += 1
    print(f"[定时任务] 启动完成，恢复 {restored} 个待执行任务")


@_driver.on_shutdown
async def _shutdown():
    global _repo

    if _scheduler.running:
        _scheduler.shutdown(wait=True)

    if _repo is not None:
        await _repo.close()
        _repo = None
