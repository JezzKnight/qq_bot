from pathlib import Path

from .loader import PromptLoader
from .renderer import PromptRenderer


class PromptService:
    """提示词服务层 — 业务代码与提示词系统之间的统一接口"""

    # 系统提示词的组装顺序，每个目录下的 .md 文件按文件名排序拼接
    _SYSTEM_CATEGORIES = (
        "persona",
        "constraints",
        "guidelines",
        "capabilities",
        "style",
    )

    def __init__(self, loader: PromptLoader, renderer: PromptRenderer) -> None:
        self._loader = loader
        self._renderer = renderer

    def get_system_prompt(self, **variables: str) -> str:
        """获取聊天系统提示词，按 persona → constraints → preferences 顺序组装"""
        template = self._assemble_from_dir("chat/system")
        return self._renderer.render(template, **variables)

    def get_group_prompt(self, **variables: str) -> str:
        """获取群聊身份规则提示词（chat/group.md）"""
        template = self._loader.load("chat/group.md")
        return self._renderer.render(template, **variables)

    def get_agent_prompt(self, agent_name: str, **variables: str) -> str:
        """获取子 Agent 提示词（agents/{agent_name}.md）"""
        template = self._loader.load(f"agents/{agent_name}.md")
        return self._renderer.render(template, **variables)

    def _assemble_from_dir(self, relative_dir: str) -> str:
        """从目录加载所有分类子目录下的 .md 片段，按顺序拼接。

        relative_dir 下按 _SYSTEM_CATEGORIES 顺序扫描各子目录，
        每个子目录内的 .md 文件按文件名排序读取。
        只包含 .md 后缀的文件（.disabled、.md.bak 等会被忽略），
        方便通过重命名来热插拔特定规则。
        """
        base = self._loader.base_dir / relative_dir
        parts: list[str] = []
        for category in self._SYSTEM_CATEGORIES:
            cat_dir = base / category
            if not cat_dir.is_dir():
                continue
            for fragment in sorted(cat_dir.glob("*.md")):
                content = fragment.read_text(encoding="utf-8")
                if content.strip():
                    parts.append(content)
        return "\n\n".join(parts)


# 模块级单例，基于 prompts 包所在目录
_base_dir = Path(__file__).parent
prompt_service = PromptService(
    loader=PromptLoader(_base_dir),
    renderer=PromptRenderer(),
)
