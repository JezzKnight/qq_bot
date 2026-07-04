
from nonebot import get_plugin_config
from ..config import AiChatConfig
from ....agents.search_agent import SearchAgent
from ..client_factory import get_client_for_model
from .registry import register_tool, get_tools_schema, TOOLS

@register_tool(
    name="search_agent",
    description="当你需要查找未知信息时调用此工具。你必须提供搜索任务描述，描述清楚：\n"
                "1. 用户真正想了解的具体话题是什么（结合对话上下文确定）\n"
                "2. 涉及的关键实体（人名、地名、事件名、产品名等，从对话中提取）\n"
                "3. 用户期望得到什么样的信息（数据、新闻、教程、百科等）\n\n"
                "注意：你不需要构造搜索关键词。子Agent会自行完成关键词提取和搜索策略。",
    parameters={"type": "object",
                "properties": {
                "task":{
                    "type": "string",
                    "description": "搜索任务描述，包含话题、关键实体、用户期望的信息类型。基于完整对话上下文来写。"
                    }
                },
                "required": ["task"]
                }
)
async def search_agent(task: str, model: str,):
    # 在此处构造client然后注入
    config = get_plugin_config(AiChatConfig)
    client = await get_client_for_model(config, model)
    # 构建sub agent的工具列表
    tools = get_tools_schema("web_search","get_current_time","web_fetch")
    subagent = SearchAgent(client, tools, model, task, TOOLS)
    search_res = await subagent.execute(fail_msg="检索任务失败")
    return search_res
