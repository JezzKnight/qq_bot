from pathlib import Path


class PromptNotFoundError(Exception):
    """提示词文件不存在"""

    def __init__(self, file_path: str) -> None:
        super().__init__(f"提示词文件不存在: {file_path}")


class PromptLoader:
    """提示词加载器 — 只负责从文件系统读取 Markdown 文件"""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def load(self, relative_path: str) -> str:
        """读取指定路径的提示词文件，返回原始文本"""
        file_path = self.base_dir / relative_path
        if not file_path.exists():
            raise PromptNotFoundError(str(file_path))
        return file_path.read_text(encoding="utf-8")
