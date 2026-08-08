from datetime import datetime

from prompts.service import prompt_service

from .base import BaseSubAgent, UsageRecorder


class SearchAgent(BaseSubAgent):
    agent_name: str = "search_agent"
    system_prompt: str  # 由 PromptService 在 __init__ 中加载
    max_rounds: int = 20

    def __init__(  # noqa: PLR0913
        self,
        client,
        tools: list[dict],
        model: str,
        task: str,
        tool_registry: dict[str, dict],
        usage_recorder: UsageRecorder | None = None,
    ) -> None:
        now = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
        self.system_prompt = prompt_service.get_agent_prompt("search", current_time=now)

        super().__init__(client, tools, model, tool_registry, usage_recorder)

        self.task = task

    def _build_task_prompt(self, **kwargs) -> str:
        """构造user输入"""
        # 两层保底，main agent没生成搜索任务内容时直接用用户输入，用户没输入就返回空
        context = kwargs.get("task") or self.task or ""
        task = f"搜索任务：{context}\n\n请开始搜索。"
        return task

