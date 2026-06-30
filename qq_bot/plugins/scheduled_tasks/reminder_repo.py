import json
import aiosqlite
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

@dataclass
class Reminder:
    """一条提醒记录"""
    id: Optional[int] = None                # 数据库自增 ID
    remind_at: str = ""                     # ISO 8601 时间 "2026-06-30T00:00:00"
    message: str = ""                       # 推送内容 "该睡觉了！"
    target_type: str = ""                   # "group" | "private"
    target_id: str = ""                     # 群号或用户 QQ 号
    creator_user_id: str = ""               # 谁创建的（用于权限控制）
    job_id: str = ""                        # APScheduler job ID，用于取消
    status: str = "pending"                 # "pending"（等待触发） | "fired"（已完成） | "cancelled"（被取消）
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

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
        conn = await self._get_conn()
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS reminders (
                id  INT PRIMARY KEY,
                remind_at  TEXT NOT NULL,
                message  TEXT NOT NULL,
                target    TEXT DEFAULT '{}'
            );
            
            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT NOT NULL,
                sender_name  TEXT,
                role         TEXT NOT NULL,
                content      TEXT,
                tool_call_id TEXT,
                tool_calls   TEXT,
                images       TEXT,
                created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );
            
            CREATE INDEX IF NOT EXISTS idx_messages_session_time
            ON messages(session_id, id);
        """)
        await conn.commit()
    
    async def close(self):
        """reminder的关闭函数"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


