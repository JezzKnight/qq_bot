from .registry import register_tool
from nonebot import get_plugin_config
from ..config import AiChatConfig
import httpx
import uuid


@register_tool(
    name="web_fetch",
    description="使用 Tavily 搜索引擎爬取网页的具体内容，当用户给出具体的网页网址的时候，使用该工具获取网页中的内容",
    parameters={"type": "object",
                "properties": {
                "urls":{    
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "爬取目标网页的具体urls列表，可以一次性爬取多个网站，要求list格式，每个url是一个元素。"
                    }},
                "required": ["urls"]
                }
)
async def web_fetch(urls: list):
    payload = {
        # 决定搜索开销
        "urls": urls, # 最多搜索结果zheg
        "extract_depth": "advanced", # 搜索模式
    }

    results = await web_fetch_by_tavily(payload)
    if not results:
        return "Error: Tavily web fetcher does not return any results."
    else:
        return _fetch_result_payload(results)


async def web_fetch_by_tavily(payload) -> dict:
    """tavily爬取操作"""
    config = get_plugin_config(AiChatConfig)
    tavily_api_key = config.Tavily_key
    url = "https://api.tavily.com/extract"
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
            print(f"[DEBUG] Tavily fetch 状态码: {response.status_code}")
            print(f"[DEBUG] Tavily fetch 响应体: {response.text[:500]}")
            return response.json()
        except httpx.ConnectTimeout:
            print(f"[ERROR] Tavily fetch 连接超时")
            return {}


def _fetch_result_payload(data: dict):
    """对搜索出来的结果做解析"""
    failed_or_not = data.get("failed_results")
    if failed_or_not:
        print(f"[WARN] 提取失败url:{failed_or_not}")
    
    res_uuid = str(uuid.uuid4())[:4]
    lines = ["以下内容为网页具体内容，请查看是否有关于问题的信息"]

    results = data.get("results", [])
    for idx, r in enumerate(results, 0):
        # 更加结构化的结果
        lines.append(
            f"{res_uuid}.{idx} 网站url：{r['url']}\n"
            f"网页内容：{r['raw_content']}\n\n"
        )

    return "\n\n".join(lines)