# sub agent基类，这个是为sub agent进行抽象基类，为后续开发多类型sub agent写的基础架构

import json
from abc import ABC, abstractmethod
from nonebot import get_plugin_config
from ..plugins.ai_chat.config import AiChatConfig
from ..ai.types import ChatMessage
from ..ai.openai_client import Openaiclient
from ..ai.gemini_client import Geminiclient

_openai_client: Openaiclient | None = None
_gemini_client: Geminiclient | None = None

class BaseSubAgent(ABC):
    """子Agent基类，本质是一个独立的LLM对话"""
    agent_name: str
    system_prompt: str
    max_rounds: int


    def __init__(self, tools: list[dict], model: str):
        super().__init__()
        self.model = model
        self.tools: list[dict] = tools # subagent可用工具列表


    @abstractmethod
    def _build_task_prompt(self, **kwargs) -> str:
        # 抽象方法中的逻辑应该留给子类实现，这里不应该写死处理方式，这里处理的是你定义工具时在工具描述中写的你所需要的参数
        pass


    def _get_client(self):
        # 选择对应客户端
        global _gemini_client, _openai_client
        config = get_plugin_config(AiChatConfig)
        if "gemini" in self.model.lower():
            if _gemini_client is None:
                _gemini_client = Geminiclient(api_key=config.gemini_api_key)
            return _gemini_client
        else:
            if _openai_client is None:
                _openai_client = Openaiclient(base_url=config.ai_base_url,
                    api_key=config.ai_api_key)
            return _openai_client


    async def execute(self, fail_msg: str, **kwargs) -> str:
        # 防止import循环
        from ..plugins.ai_chat.tools import TOOLS
        # 获取prompt，构建消息列表，循环执行
        messages = [ChatMessage(role = "system", content=self.system_prompt)]
        # 获取user信息
        # content = self._build_task_prompt(**kwargs)
        # messages.append(ChatMessage(role= "user", content=f"{content}\n请开始搜索任务。"))
        # 获取对应client
        client = self._get_client()
        for _ in range(self.max_rounds):
            response = await client.chat(
                messages=messages,
                model=self.model,
                tools=self.tools
            )
            if not response.tool_calls:
                final_content = response.content or "AI暂时无法响应"
                print(f"[INFO] Sub Agent工具最终响应：{final_content}")
                # 本轮没有工具调用触发就结束本轮循环
                break
            
            assistant_msg = ChatMessage(role="assistant", tool_calls = response.tool_calls, raw_parts=response.raw_parts)
            messages.append(assistant_msg)

            # print(f"[INFO] 工具调用：{response.tool_calls}")
            for tc in response.tool_calls:
                func = tc["function"]
                tool = TOOLS[func["name"]]
                args = json.loads(func["arguments"])
                result = await tool["func"](**args)

                messages.append(ChatMessage(
                    role = "tool",
                    content = result,
                    tool_call_id = tc["id"],
                ))
        # for循环正常break就忽略else，未触发循环结束则触发else
        else:
            final_content = fail_msg
            return final_content
        
        return final_content
        


            

