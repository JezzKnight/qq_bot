from pathlib import Path
from .config import AiChatConfig
from ...memory.manager import MemoryManager
from ...memory.sqlite_repo import SqliteRepository
from ...memory.repository import MemoryRepository
from nonebot_plugin_localstore import get_plugin_data_dir

_Memory: MemoryManager | None = None

async def get_memory(config: AiChatConfig) -> MemoryManager:
    """组装车间"""
    repo: MemoryRepository
    global _Memory
    if _Memory is not None:
        return _Memory

    if config.memory_backend == "sqlite":
        repo = SqliteRepository(db_path=Path(get_plugin_data_dir()) / "ai_chat" / "memory.db")
    else:
        raise ValueError(f"不支持的后端类型：{config.memory_backend}")
        
    await repo.init()
    _Memory = MemoryManager(repository=repo, max_history=config.max_history,)
    return _Memory