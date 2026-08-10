"""术语库（glossary）：按群存储「词汇 → 含义」，供动态注入做关键词匹配。

存储位置：long_term_memory/groups/{group_id}/glossary.json
写入方：save_glossary 工具（AI 调用）；读取方：dynamic_injection 注入链路。
"""
import json
import re
from datetime import datetime
from pathlib import Path

from nonebot_plugin_localstore import get_plugin_data_dir


def _term_hit(term: str, text_lower: str) -> bool:
    """短 ASCII 词（≤3 纯字母）要求词边界，避免 'as'/'go' 误伤；其余子串匹配。"""
    if not term:
        return False
    if len(term) <= 3 and term.isascii() and term.isalpha():
        return re.search(
            rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text_lower
        ) is not None
    return term.lower() in text_lower


class GlossaryStore:
    """per-group 术语库：存储 / 匹配 / 注入 / 写入 API。"""

    __slots__ = ("_file", "group_id")

    def __init__(self, group_id: int | str) -> None:
        self.group_id = str(group_id)
        self._file: Path = (
            get_plugin_data_dir()
            / "long_term_memory"
            / "groups"
            / self.group_id
            / "glossary.json"
        )

    def load(self) -> list[dict]:
        """读取全部术语 [{term, definition, ...}]；文件缺失/损坏返回 []。"""
        if not self._file.exists():
            return []
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] 术语库读取失败: {self._file} ({e})")
            return []
        terms = data.get("terms", []) if isinstance(data, dict) else []
        return terms if isinstance(terms, list) else []

    def match(self, text: str) -> list[dict]:
        """在 text 中匹配术语，按 term 长度降序返回命中项。"""
        terms = self.load()
        if not terms or not text:
            return []
        text_lower = text.lower()
        hits = [t for t in terms if _term_hit(str(t.get("term", "")), text_lower)]
        hits.sort(key=lambda t: len(str(t.get("term", ""))), reverse=True)
        return hits

    def add_term(self, term: str, definition: str) -> None:
        """写入术语：已存在则覆盖 definition+updated，否则追加；目录自动创建。"""
        terms = self.load()
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        for t in terms:
            if str(t.get("term", "")) == term:
                t["definition"] = definition
                t["updated"] = now
                break
        else:
            terms.append({
                "term": term,
                "definition": definition,
                "created": now,
                "updated": now,
            })
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps({"terms": terms}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def format_injection(terms: list[dict]) -> str:
        """生成术语注入块：## 群术语 + - 「term」：definition。"""
        lines = ["## 群术语"]
        for t in terms:
            lines.append(f"- 「{t.get('term', '')}」：{t.get('definition', '')}")
        return "\n".join(lines)
