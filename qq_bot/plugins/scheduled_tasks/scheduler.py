from apscheduler.schedulers.asyncio import AsyncIOScheduler


class SchedulerGateway:
    """调度器网关：封装 APScheduler，提供语义清晰的接口"""

    def __init__(self, scheduler: AsyncIOScheduler):
        self._scheduler = scheduler

    def add_reminder(self, job_id: str, run_at, callback):
        """注册一次性提醒 job —— job_id 自动作为回调参数传入"""
        self._scheduler.add_job(
            func=callback,
            trigger="date",
            run_date=run_at,
            id=job_id,
            args=[job_id],
            misfire_grace_time=60,
            replace_existing=True,
        )

    def remove_reminder(self, job_id: str) -> bool:
        """移除提醒 job，不存在返回 False"""
        job = self._scheduler.get_job(job_id)
        if job is None:
            return False
        job.remove()
        return True

    def shutdown(self, wait: bool = True):
        """关闭调度器"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)

    @property
    def running(self) -> bool:
        return self._scheduler.running