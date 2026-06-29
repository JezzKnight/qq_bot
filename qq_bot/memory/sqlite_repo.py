import json
import aiosqlite
import asyncio
from pathlib import Path
from .repository import MemoryRepository  # 导入接口（可选，Protocol 不强制继承）


class SqliteRepository:  # 不需要显式写 (MemoryRepository)
    """实现 MemoryRepository 协议的 SQLite 后端"""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    # ──── 私有方法（接口里没有，SqliteRepository 独有）────
    async def _get_conn(self) -> aiosqlite.Connection:
        """获取数据库连接，惰性初始化 + WAL 模式"""
        if self._conn is not None:
            return self._conn
        # 添加异步锁并发保护
        async with self._lock:
            if self._conn is not None:
                return self._conn
            self._conn = await aiosqlite.connect(str(self._db_path))
            # 使用Row工厂，查询结果变成类似字典对象
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL;")
            await self._conn.execute("PRAGMA foreign_keys=ON;")
        return self._conn

    # ──── 公有方法（每一条都对应接口协议）────
    async def init(self) -> None:
        conn = await self._get_conn()
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id  TEXT PRIMARY KEY,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                metadata    TEXT DEFAULT '{}'
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


    async def get_messages(self, session_id: str, limit: int | None = None) -> list[dict]:
        conn = await self._get_conn()
        # SQL 查询逻辑
        if limit is not None:
            cursor = await conn.execute(
            """SELECT id, role, sender_name, content, tool_call_id, tool_calls, images
                FROM (
                    SELECT id, role, sender_name, content, tool_call_id, tool_calls, images
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?                    
                )
                ORDER BY id ASC""",
                (session_id, limit),
            )
        else:
            cursor = await conn.execute(
            """
            SELECT role, sender_name, content, tool_call_id, tool_calls, images
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC""",
            (session_id,),)
        # fetchall一次性获取所有数据
        rows = await cursor.fetchall()
        result = []
        # 解析数据库数据，构造历史数据
        for row in rows:
            msg = {"role":row["role"], "content":row["content"]}
            if row["sender_name"] is not None:
                msg["sender_name"] = row["sender_name"]
            if row["tool_call_id"] is not None:
                msg["tool_call_id"] = row["tool_call_id"]
            if row["tool_calls"] is not None:
                msg["tool_calls"] = json.loads(row["tool_calls"])
            if row["images"] is not None:
                msg["images"] = json.loads(row["images"])
            result.append(msg)
        return result


    async def add_messages(self, session_id: str, messages: list[dict]) -> None:
        """记录新增记忆"""
        conn = await self._get_conn()
        await conn.execute("BEGIN")
        try:
            # 维护updated_at，移动到循环外面来保证原子性，先父后子
            await conn.execute(
                """INSERT INTO sessions (session_id, created_at, updated_at)
                    VALUES (?, datetime('now'), datetime('now'))
                    ON CONFLICT(session_id) DO UPDATE SET updated_at = datetime('now')""",
                (session_id,),
            )

            for msg in messages:
                # 显式事务
                await conn.execute(
                """INSERT INTO messages (session_id, sender_name, role, content, tool_call_id, tool_calls, images)
                    VALUES (?,?,?,?,?,?,?)""",
                    (
                        session_id,
                        msg.get("sender_name"),
                        msg["role"],
                        msg.get("content"),
                        msg.get("tool_call_id"),
                        json.dumps(msg["tool_calls"]) if msg.get("tool_calls") else None,
                        json.dumps(msg["images"]) if msg.get("images") else None,
                    ),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        
        


    async def delete_session(self, session_id: str) -> None:
        """SQL 删除"""
        conn = await self._get_conn()
        await conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await conn.commit()


    async def get_message_count(self, session_id: str) -> int:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
        )
        # fetchone一次获取一行
        row = await cursor.fetchone()
        return row[0] if row else 0


    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None