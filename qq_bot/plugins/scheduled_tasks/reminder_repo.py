import aiosqlite
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

@dataclass
class Reminder:
    """一条提醒记录"""
    id: int | None = None                # 数据库自增 ID
    remind_at: str = ""                  # ISO 8601 时间 "2026-06-30T00:00:00"
    task_type: str = "reminder"          # "reminder"（简单提醒）| "agent_task"（智能任务）
    message: str = ""                    # 推送内容 "该睡觉了！"
    target_type: str = ""                # "group" | "private"
    target_id: str = ""                  # 群号或用户 QQ 号
    creator_user_id: str = ""            # 谁创建的（用于权限控制）
    job_id: str = ""                     # APScheduler job ID，用于取消
    status: str = "pending"              # "pending"（等待触发） | "fired"（已完成） | "cancelled"（被取消）
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

def _row_to_reminder(row) -> Reminder:
    """将数据库行转换为 Reminder 对象"""
    return Reminder(
        id=row["id"],
        task_type=row["task_type"],
        remind_at=row["remind_at"],
        message=row["message"],
        target_type=row["target_type"],
        target_id=row["target_id"],
        creator_user_id=row["creator_user_id"],
        job_id=row["job_id"],
        status=row["status"],
        created_at=row["created_at"],
    )


class ReminderRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._conn:Optional[aiosqlite.Connection] = None


    async def _get_conn(self) -> aiosqlite.Connection:
        """获取储存计划任务的数据库连接"""
        if self._conn is not None:
            return self._conn
        
        async with self._lock:
            if self._conn is not None:
                return self._conn
            self._conn = await aiosqlite.connect(str(self.db_path))
            # 使用Row工厂，查询结果变成类似字典对象
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL;")
            await self._conn.execute("PRAGMA foreign_keys=ON;")
        return self._conn
    

    async def init(self) -> None:
        """初始化表"""
        conn = await self._get_conn()
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS reminders (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type       TEXT NOT NULL,
                remind_at       TEXT NOT NULL,
                message         TEXT NOT NULL,
                target_type     TEXT NOT NULL DEFAULT '',
                target_id       TEXT NOT NULL DEFAULT '',
                creator_user_id TEXT NOT NULL DEFAULT '',
                job_id          TEXT NOT NULL DEFAULT '',
                status          TEXT NOT NULL DEFAULT 'pending',
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_reminders_job_id
            ON reminders(job_id);

            CREATE INDEX IF NOT EXISTS idx_reminders_status_remind_at
            ON reminders(status, remind_at);
        """)
        await conn.commit()
    

    async def save(self, r:Reminder) -> Reminder:
        """保存schedule数据到数据库"""
        conn = await self._get_conn()
        cursor = await conn.execute(
            """
            INSERT INTO reminders
            (task_type, remind_at, message, target_type, target_id, creator_user_id, job_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (r.task_type, r.remind_at, r.message, r.target_type, r.target_id, r.creator_user_id, r.job_id, r.status, r.created_at)
        )
        r.id = cursor.lastrowid #?
        await conn.commit()
        return r
    

    async def mark_fired(self, job_id):
        """状态流转，将任务状态设定为'已完成'"""
        conn = await self._get_conn()
        await conn.execute(
            "UPDATE reminders SET status='fired' WHERE job_id=?",
            (job_id,),
        )
        await conn.commit()


    async def cancel(self, job_id) -> bool:
        """状态流转，将'待执行'任务状态设定为'取消'"""
        conn = await self._get_conn()
        cursor = await conn.execute(
            "UPDATE reminders SET status='cancelled' WHERE job_id=? AND status='pending'",
            (job_id,),
        )
        await conn.commit()
        return cursor.rowcount > 0


    async def get_all_pending(self) -> list[Reminder]:
        """bot 重启时用：加载所有未触发的提醒"""
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM reminders WHERE status='pending' AND remind_at > ?",
            (datetime.now().isoformat(),), #?
        )
        rows = await cursor.fetchall()
        return [_row_to_reminder(row) for row in rows]

    async def get_by_job_id(self, job_id) -> Optional[Reminder]:
        """通过job_id来获取定时任务详情"""
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM reminders WHERE job_id=?",
            (job_id,),
        )
        info = await cursor.fetchone()
        if info is None:
            return None
        return _row_to_reminder(info)


    async def get_by_target(
        self, target_type: str, target_id: str, status: str | None = None,
    ) -> list[Reminder]:
        """查询指定目标（群/私聊）的提醒列表，按触发时间升序"""
        conn = await self._get_conn()
        if status is not None:
            cursor = await conn.execute(
                """SELECT * FROM reminders
                   WHERE target_type = ? AND target_id = ? AND status = ?
                   ORDER BY remind_at ASC""",
                (target_type, target_id, status),
            )
        else:
            cursor = await conn.execute(
                """SELECT * FROM reminders
                   WHERE target_type = ? AND target_id = ?
                   ORDER BY remind_at ASC""",
                (target_type, target_id),
            )
        rows = await cursor.fetchall()
        return [_row_to_reminder(row) for row in rows]

    async def close(self):
        """reminder的关闭函数"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


