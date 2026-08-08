"""Token 用量统计 —— 按天汇总，持久化到 SQLite。

设计:
- 每次 LLM API 调用成功后，将输入/输出 token 累加到当天一行（UPSERT）
- 输入缓存命中 = cached_tokens
- 输入缓存未命中 = prompt_tokens - cached_tokens（查询时计算）
- 按配置保留天数自动清理过期数据（启动时 + 每天惰性一次）
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

import aiosqlite
from nonebot import get_plugin_config
from nonebot_plugin_localstore import get_plugin_data_dir

from .config import AiChatConfig

logger = logging.getLogger(__name__)


class TokenUsageRepository:
    """按天汇总 token 用量的 SQLite 仓库"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        """懒获取连接，双检锁避免并发重复连接"""
        if self._conn is not None:
            return self._conn
        async with self._lock:
            if self._conn is not None:
                return self._conn
            # SQLite 不会自动创建父目录，需先确保目录存在
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(str(self.db_path))
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL;")
            await self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS token_usage (
                    day TEXT PRIMARY KEY,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    cached_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await self._conn.commit()
        return self._conn

    async def init(self) -> None:
        """启动时调用，确保表已创建"""
        await self._get_conn()

    async def accumulate(
        self, day: str, prompt_tokens: int, cached_tokens: int, completion_tokens: int
    ) -> None:
        """将本次调用的 token 累加到当天（UPSERT）"""
        conn = await self._get_conn()
        await conn.execute(
            # excluded. 是用于插入新数据的，如果不加那这个 prompt_tokens 就还是
            # 表中的数据而不是新的数据
            """
            INSERT INTO token_usage
                (day, prompt_tokens, cached_tokens, completion_tokens, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(day) DO UPDATE SET
                prompt_tokens = prompt_tokens + excluded.prompt_tokens,
                cached_tokens = cached_tokens + excluded.cached_tokens,
                completion_tokens = completion_tokens + excluded.completion_tokens,
                updated_at = excluded.updated_at
            """,
            (
                day, # 这里的day并不会做什么修改仅用于确认数据日期
                prompt_tokens,
                cached_tokens,
                completion_tokens,
                datetime.now().astimezone().isoformat(),
            ),
        )
        await conn.commit()

    async def get_someday(self, date: str) -> dict | None:
        """查询某天的用量，无记录返回 None"""
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT day, prompt_tokens, cached_tokens, completion_tokens "
            "FROM token_usage WHERE day = ?",
            (date,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "day": row["day"],
            "prompt_tokens": row["prompt_tokens"],
            "cached_tokens": row["cached_tokens"],
            "completion_tokens": row["completion_tokens"],
        }

    async def cleanup(self, before_day: str) -> None:
        """删除早于 before_day 的过期记录"""
        conn = await self._get_conn()
        await conn.execute("DELETE FROM token_usage WHERE day < ?", (before_day,))
        await conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


class _UsageState:
    """模块级单例状态（属性赋值规避 global 告警）"""

    repo: TokenUsageRepository | None = None
    last_cleanup_day: str = ""


_state = _UsageState()


async def init() -> None:
    """初始化仓库（幂等）：建表 + 启动清理"""
    if _state.repo is not None:
        return
    db_path = Path(get_plugin_data_dir()) / "ai_chat" / "usage" / "token_usage.db"
    repo = TokenUsageRepository(db_path)
    await repo.init()
    _state.repo = repo
    await _maybe_cleanup(_today())


async def record(
    prompt_tokens: int, cached_tokens: int, completion_tokens: int
) -> None:
    """记录一次 API 调用的 token 消耗，累加到当天。失败请求（全 0）跳过。"""
    if prompt_tokens + completion_tokens == 0:
        return
    if _state.repo is None:
        await init()
    # 二次校验数据库连接状态，防止出现以下：数据库连接失败、配置错误、
    # init() 内部异常被捕获但未重新引发
    if _state.repo is None:
        return
    await _state.repo.accumulate(
        _today(), prompt_tokens, cached_tokens, completion_tokens
    )
    await _maybe_cleanup(_today())


async def get_date_summary(date: str) -> dict:
    """返回特定日期的用量汇总，无记录时返回全 0"""
    if _state.repo is None:
        await init()
    if _state.repo is None:
        return _empty_summary(date)
    row = await _state.repo.get_someday(date)
    return row or _empty_summary(date)


async def close() -> None:
    """关闭仓库连接（生命周期结束时调用）"""
    if _state.repo is not None:
        await _state.repo.close()
        _state.repo = None


def _today() -> str:
    """本地日期，格式 YYYY-MM-DD"""
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def _empty_summary(today: str) -> dict:
    return {
        "day": today,
        "prompt_tokens": 0,
        "cached_tokens": 0,
        "completion_tokens": 0,
    }


async def _maybe_cleanup(today: str) -> None:
    """按配置保留天数清理过期数据，每天最多执行一次"""
    if _state.repo is None:
        return
    if _state.last_cleanup_day == today:
        return
    _state.last_cleanup_day = today

    retention = get_plugin_config(AiChatConfig).token_usage_retention_days
    if retention <= 0:
        return
    before_day = (
        datetime.now().astimezone() - timedelta(days=retention)
    ).strftime("%Y-%m-%d")
    try:
        await _state.repo.cleanup(before_day)
    except Exception:  # noqa: BLE001
        logger.warning("token_usage 过期数据清理失败", exc_info=True)
