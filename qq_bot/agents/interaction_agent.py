from datetime import datetime
from zoneinfo import ZoneInfo

from prompts.service import prompt_service

from .base import BaseSubAgent, UsageRecorder


class InteractionAgent(BaseSubAgent):
    """单发开场白生成子 Agent：只输出一条发给目标成员 A 的 QQ 开场消息。

    上下文隔离：看不到群聊流水与委托人，只注入 A 的显示名 / 记忆画像 / 话题。
    tools=[] 且 max_rounds=1 —— 一次性文本生成，绝不触发多轮工具链，
    从根本上避免把"委托者要什么"与"以 bot 身份对 A 说什么"混在同一思维链里。
    """

    agent_name: str = "interaction_agent"
    system_prompt: str  # 由 PromptService 在 __init__ 中加载
    max_rounds: int = 1

    def __init__(  # noqa: PLR0913
        self,
        client: object,
        tools: list[dict],
        model: str,
        *,
        target_name: str,
        target_memory: str,
        topic: str,
        tone: str,
        tool_registry: dict[str, dict],
        usage_recorder: UsageRecorder | None = None,
    ) -> None:
        now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y年%m月%d日 %H:%M:%S")
        self.system_prompt = prompt_service.get_agent_prompt(
            "interaction",
            current_time=now,
            target_name=target_name,
            target_memory=target_memory,
            topic=topic,
            tone=tone,
        )

        super().__init__(client, tools, model, tool_registry, usage_recorder)

    def _build_task_prompt(self, **_kwargs: object) -> str:
        """返回用户消息——开场白上下文已全部注入 system_prompt，这里仅要求直接输出正文"""
        return "现在，直接输出那一条开场消息正文本身。"
