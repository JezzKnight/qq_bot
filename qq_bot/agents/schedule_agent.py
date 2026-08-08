from datetime import datetime

from prompts.service import prompt_service

from .base import BaseSubAgent, UsageRecorder


class ScheduleTaskAgent(BaseSubAgent):
    agent_name: str = "schedule_agent"
    system_prompt: str  # 由 PromptService 在 __init__ 中加载
    max_rounds: int = 3

    def __init__(  # noqa: PLR0913
        self,
        client,
        tools: list[dict],
        model: str,
        prompt: str,
        tool_registry: dict[str, dict],
        usage_recorder: UsageRecorder | None = None,
    ) -> None:
        now = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
        self.system_prompt = prompt_service.get_agent_prompt("schedule", current_time=now, user_task=prompt)

        super().__init__(client, tools, model, tool_registry, usage_recorder)


    def _build_task_prompt(self, **kwargs) -> str:
        """返回用户消息——简单告知开始执行即可，核心意图已经在 system_prompt 里"""
        return f"请开始执行上述任务。当前时间：{datetime.now().isoformat()}"
