from datetime import datetime
from zoneinfo import ZoneInfo

from prompts.service import prompt_service

from .base import BaseSubAgent, UsageRecorder


class ImageEditAgent(BaseSubAgent):
    """图像编辑指令精修子 Agent：把口语化改图需求转成一条可执行指令。

    tools=[] 且 max_rounds=1 —— 一次性文本生成，不触发工具链。
    与主对话隔离：拿到的是"用户原话 + 图片角色约定"，不背聊天流水，
    避免把闲聊内容混进对画面的要求（对齐 InteractionAgent 的隔离思路）。
    """

    agent_name: str = "image_edit_agent"
    system_prompt: str  # 由 PromptService 在 __init__ 中加载
    max_rounds: int = 1

    def __init__(  # noqa: PLR0913  Agent 构造参数逐项来自本次任务上下文
        self,
        client: object,
        tools: list[dict],
        model: str,
        *,
        user_request: str,
        image_count: int,
        base_index: int,
        reference_indexes: list[int],
        tool_registry: dict[str, dict],
        usage_recorder: UsageRecorder | None = None,
    ) -> None:
        now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y年%m月%d日 %H:%M:%S")
        if reference_indexes:
            refs = "、".join(f"图{i}" for i in reference_indexes)
            mode_desc = "多图修改：一张被修改的原图 + 若干参照图"
        else:
            refs = "无"
            mode_desc = "单图修改：只有一张被修改的原图，没有参照图"

        self.system_prompt = prompt_service.get_agent_prompt(
            "image_edit",
            current_time=now,
            mode_desc=mode_desc,
            image_count=str(image_count),
            base_index=str(base_index),
            reference_indexes=refs,
            user_request=user_request,
        )

        super().__init__(client, tools, model, tool_registry, usage_recorder)

    def _build_task_prompt(self, **_kwargs: object) -> str:
        """任务上下文已全部注入 system_prompt，这里只要求输出指令正文"""
        return "现在，直接输出那一条交给图像编辑模型的指令正文。"
