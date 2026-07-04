# sub agent基类，这个是为sub agent进行抽象基类，为后续开发多类型sub agent写的基础架构

import json
from abc import ABC, abstractmethod
from ..ai.types import ChatMessage


class BaseSubAgent(ABC):
    """子Agent基类，本质是一个独立的LLM对话"""
    agent_name: str
    system_prompt: str
    max_rounds: int


    def __init__(self, client, tools: list[dict], model: str, tool_registry: dict[str, dict]):
        super().__init__()
        self.model = model
        self.client = client
        self.tool_registry = tool_registry
        self.tools: list[dict] = tools # subagent可用工具列表


    @abstractmethod
    def _build_task_prompt(self, **kwargs) -> str:
        # 抽象方法中的逻辑应该留给子类实现，这里不应该写死处理方式，这里处理的是你定义工具时在工具描述中写的你所需要的参数
        pass


    async def execute(self, fail_msg: str, **kwargs) -> str:
        # 获取prompt，构建消息列表，循环执行
        messages = [ChatMessage(role = "system", content=self.system_prompt)]
        # 获取user信息
        content = self._build_task_prompt(**kwargs)
        # 做一个空内容的兜底
        if content:
            messages.append(ChatMessage(role= "user", content=content))
        try:
            for _ in range(self.max_rounds):
                response = await self.client.chat(
                    messages=messages,
                    model=self.model,
                    tools=self.tools
                )
                # 如果没有工具调用，则直接返回内容
                if not response.tool_calls:
                    final_content = response.content or "AI暂时无法响应"
                    break
                
                assistant_msg = ChatMessage(role="assistant", tool_calls = response.tool_calls, raw_parts=response.raw_parts)
                messages.append(assistant_msg)

                # print(f"[INFO] 工具调用：{response.tool_calls}")
                for tc in response.tool_calls:
                    func = tc["function"]
                    # 工具改为由构造器注入
                    # tool = TOOLS[func["name"]]
                    tool = self.tool_registry[func["name"]]
                    args = json.loads(func["arguments"])
                    result = await tool["func"](**args)

                    messages.append(ChatMessage(
                        role = "tool",
                        content = result,
                        tool_call_id = tc["id"],
                    ))
            else:
                final_content = fail_msg
                return final_content
        
        except Exception as e:
            import traceback
            print(f"[ERROR] Sub Agent '{self.agent_name}' 执行异常: {type(e).__name__}: {e}")
            traceback.print_exc()
            final_content = f"{fail_msg}（原因：{e}）"
        
        return final_content
        


            

