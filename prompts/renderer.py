import re


class PromptRenderer:
    """提示词渲染器 — 只负责将模板中的 {{ variable }} 替换为实际值"""

    _VAR_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")

    def render(self, template: str, **variables: str) -> str:
        """替换模板变量，未提供的变量保留原文"""

        def _replace(match: re.Match) -> str:
            key = match.group(1)
            if key in variables:
                return variables[key]
            return match.group(0)  # 变量未提供时保留原文，方便调试

        return self._VAR_PATTERN.sub(_replace, template)
