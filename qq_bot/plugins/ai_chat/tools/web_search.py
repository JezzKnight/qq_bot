from .registry import register_tool
from typing import Literal
from nonebot import get_plugin_config
from ..config import AiChatConfig
import httpx
import uuid


@register_tool(
    name="web_search",
    description="使用 Tavily 搜索引擎在互联网上查找最新或通用的网页信息。可以根据用户意图自动判断搜索类型、时效性和网站过滤。",
    parameters={"type": "object",
                "properties": {
                "query":{    
                    "type": "string",
                    "description": "搜索查询词。必须从用户对话中提炼出最核心的关键词，生成简洁、精准、适合搜索引擎的短语。例如用户说‘我想了解一下气候变化对北极熊的影响’，query 应为‘气候变化 北极熊 影响’。"
                    },
                "topic":{
                    "type": "string",
                    "enum": ["general", "news", "finance"],
                    "description": "结果类别。时效性或赛事设为 'news'，百科/资料设为 'general'。"
                    },
                    # === 新增：域名过滤参数 ===
                "exclude_domains":{
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "强制限制搜索的域名黑名单。避免低质量的信息来源"
                    }},
                "required": ["query"]
                }
)
async def web_search(query: str, 
                    topic: Literal["general", "news", "finance"] = "general", 
                    exclude_domains: list[str] | None = None):
    payload = {
        # 决定搜索开销
        "max_results": 10, # 最多搜索结果
        "search_depth": "advanced", # 搜索模式
        "include_favicon": False, # 包含每个搜索结果的图标
        "include_answer": False, # 输出带有Tavily LLM自带的问题总结
        "include_raw_content": False, # 网站原生内容，容易包含大量噪音
        "exclude_domains": ["deadspin.com"],
        # 决定搜索方向
        "query": query,
        "topic": topic, # 搜索类型
    }
    if exclude_domains:
        payload["exclude_domains"] = exclude_domains

    results = await web_search_by_tavily(payload)
    if not results:
        return "Error: Tavily web searcher does not return any results."
    else:
        return _search_result_payload(results)


async def web_search_by_tavily(payload) -> dict:
    """
    tavily搜索操作
    """
    config = get_plugin_config(AiChatConfig)
    tavily_api_key = config.Tavily_key
    url = "https://api.tavily.com/search"
    header = {
        "Authorization": f"Bearer {tavily_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        try:
            response = await client.post(
                url=url,
                headers=header,
                json=payload,
            )
            return response.json()
        except httpx.ConnectTimeout:
            return {}


def _search_result_payload(data: dict):
    """
    对搜索出来的结果做解析
    """
    lines = []

    answer = data.get("answer")
    if answer:
        lines.append(f"AI 简单总结: {answer}\n")

    results = data.get("results", [])
    for idx, r in enumerate(results, 1):
        # 更加结构化的结果
        lines.append(
            f"{idx}.{r['title']}\n"
            f"URL:{r['url']}\n"
            f"摘要:{r['content']}\n"
            
        )

    return "\n\n".join(lines)
