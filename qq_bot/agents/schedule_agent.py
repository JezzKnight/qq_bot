from .base import BaseSubAgent
from datetime import datetime


class ScheduleTaskAgent(BaseSubAgent):
    agent_name: str = "schedule_agent"
    system_prompt: str = """
    你是一个定时任务助手。用户在之前委托你执行一项任务，现在到了执行时间。

    ## 背景
    当前时间：{current_time}

    ## 用户的任务要求
    {user_task}

    ## 核心规则
    1. 你必须使用工具来获取真实信息，严禁编造任何数据
    2. 如果任务涉及查询天气、新闻、网页内容等，必须调用对应工具
    3. 最终回复要友好、完整，让用户一看就知道任务已完成
    4. 如果多次尝试仍然无法完成任务，诚实告知用户原因
    5. 回复中标注信息获取的时间和来源
    
    ## 工具选择规则
    - 如果要求你进行聊天内容总结，可以通过 `query_chat_history` 工具来获取对应聊天记录并总结，在总结的时候需要**区分不同用户**
    - 如果任务要求需要获取信息，可以通过 `search_agent` 工具来搜集信息

    ## 输出格式
    - 开头简要说明"这是你之前设置的定时任务"
    - 中间是任务的实际结果

    """
    max_rounds: int = 3

    def __init__(self, client, tools: list[dict], model: str, prompt: str, tool_registry: dict[str, dict]):
        # 注入当前时间和用户意图
        now = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
        prompt_with_time = self.system_prompt.replace("{current_time}", now)
        prompt_with_time = prompt_with_time.replace("{user_task}", prompt)

        # 临时替换类属性（不影响其他实例）
        self.system_prompt = prompt_with_time

        super().__init__(client, tools, model, tool_registry)

    
    def _build_task_prompt(self, **kwargs) -> str:
        """返回用户消息——简单告知开始执行即可，核心意图已经在 system_prompt 里"""
        return f"请开始执行上述任务。当前时间：{datetime.now().isoformat()}"
    
