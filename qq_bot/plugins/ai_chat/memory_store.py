"""长期记忆存储：按 scope 一个 JSON 文件。

scope → long_term_memory/{scope}.json：
  groups/{gid}/{uid}   个人记忆
  groups/{gid}/_group  群公共记忆
  private/{uid}        私聊记忆

写入方：save_memory 工具（AI 调用）；读取方：dynamic_injection 注入链路。
与 glossary.py 的 per-群 JSON 存储模式一致。
"""
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from nonebot_plugin_localstore import get_plugin_data_dir

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def _now() -> str:
    """本地时间 ISO 字符串（含时区，满足 DTZ005）。"""
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S")


class MemoryStore:
    """per-scope 长期记忆：load / upsert（新增·更新·删除）。"""

    __slots__ = ("_file", "scope")

    def __init__(self, scope: str) -> None:
        self.scope = scope
        self._file: Path = get_plugin_data_dir() / "long_term_memory" / f"{scope}.json"

    def load(self) -> list[dict]:
        """读取全部记忆条目；文件缺失/损坏返回空列表。"""
        if not self._file.exists():
            return []
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001  文件损坏时降级为空列表
            logger.warning("长期记忆读取失败: %s", self._file, exc_info=True)
            return []
        memories = data.get("memories", []) if isinstance(data, dict) else []
        return memories if isinstance(memories, list) else []

    def upsert(self, key: str, mem_type: str, content: str) -> str:
        """新增/更新/删除一条记忆，返回动作文案。

        - content 非空且 key 已存在 → 更新 content/mem_type/updated
        - content 非空且 key 不存在 → 新增
        - content 为空 → 删除该 key 条目（key 不存在则为空操作）
        """
        memories = self.load()
        now = _now()
        for m in memories:
            if str(m.get("key", "")) == key:
                if not content.strip():
                    memories.remove(m)
                    self._write(memories)
                    return f"已删除记忆：{key}"
                m["content"] = content
                m["mem_type"] = mem_type
                m["updated"] = now
                self._write(memories)
                return f"已更新记忆：{key}"
        if not content.strip():
            return f"记忆不存在：{key}"
        memories.append({
            "key": key,
            "mem_type": mem_type,
            "content": content,
            "created": now,
            "updated": now,
        })
        self._write(memories)
        return f"已新增记忆：{key}"

    def _write(self, memories: list[dict]) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps({"memories": memories}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
