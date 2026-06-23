
from nonebot import get_plugin_config
from ....agents.search_agent import SearchAgent
from . import register_tool, get_tools_schema

@register_tool(
    name="search_agent",
    description="这是一个辅助 sub agent ，专职于工具 'web_search' 的的使用，通过 Tavily 搜索引擎在互联网上查找最新或通用的网页信息。",
    parameters={"type": "object",
                "properties": {
                # "task":{
                #     "type": "string",
                #     "description": "搜索任务描述，直接传入用户的原始问题，不要其他内容。"
                #     }
                },
                # "required": ["task"]
                }
)
async def search_agent(task: str, model: str,):
    # 构建sub agent的工具列表
    tools = get_tools_schema("web_search","get_current_time","web_fetch")
    subagent = SearchAgent(tools, model, task)
    search_res = await subagent.execute(fail_msg="检索任务失败")
    return search_res
