import asyncio
import re
from typing import Literal

from .context import current_search_tracker
from .registry import register_tool
from .web_search import _search_result_payload, web_search_by_tavily


def _build_payload(query: str, topic: str, exclude_domains: list[str] | None) -> dict:
    """构造单次 Tavily 搜索的请求参数（与 web_search 保持一致）"""
    payload = {
        # 决定搜索开销
        "max_results": 8,  # 最多搜索结果
        "search_depth": "advanced",  # 搜索模式
        "include_favicon": False,  # 包含每个搜索结果的图标
        "include_answer": False,  # 输出带有Tavily LLM自带的问题总结
        "include_raw_content": False,  # 网站原生内容，容易包含大量噪音
        "exclude_domains": ["deadspin.com"],
        # 决定搜索方向
        "query": query,
        "topic": topic,  # 搜索类型
    }
    if exclude_domains:
        payload["exclude_domains"] = exclude_domains
    return payload


def _normalize_url(url: str) -> str:
    """URL 规范化（去尾部斜杠/查询参数/锚点），用于精确去重"""
    # return url.rstrip("/").split("?")[0].split("#")[0]
    return url.rstrip("/")


def _normalize_title(title: str) -> str:
    """标题规范化（去标点/空白/大小写），用于近重复去重"""
    return re.sub(r"\W+", "", title.lower())


@register_tool(
    name="batch_search",
    description="同时执行多个方向的网络搜索，返回合并去重后的全部结果。"
                "当需要从多个角度/关键词查询信息时使用，一次调用完成，避免逐条搜索。",
    parameters={"type": "object",
                "properties": {
                "queries":{
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "多个独立搜索方向的关键词列表，"
                                    "每个元素是一个搜索 query。"
                    },
                "topic":{
                    "type": "string",
                    "enum": ["general", "news", "finance"],
                    "description": "结果类别。时效性或赛事设为 'news'，"
                                    "百科/资料设为 'general'。"
                    },
                "exclude_domains":{
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "强制限制搜索的域名黑名单。避免低质量的信息来源"
                    }},
                "required": ["queries"]
                }
)
async def batch_search(
    queries: list[str],
    topic: Literal["general", "news", "finance"] = "general",
    exclude_domains: list[str] | None = None,
) -> str:
    """并行执行多个搜索方向，合并结果并按 URL/标题去重，全量返回。"""
    if not queries:
        return "Error: queries 不能为空。"

    # 并行执行所有方向的搜索，单个失败不影响其他方向
    results = await asyncio.gather(
        *(
            web_search_by_tavily(_build_payload(q, topic, exclude_domains))
            for q in queries
        ),
        return_exceptions=True,
    )

    tracker = current_search_tracker.get()
    merged: list[dict] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    success = False

    for res in results:
        if isinstance(res, BaseException) or not res or not res.get("results"):
            if tracker is not None:
                tracker["tavily_error_count"] += 1
            continue
        success = True
        for r in res["results"]:
            norm_url = _normalize_url(r["url"])
            norm_title = _normalize_title(r["title"])
            if norm_url in seen_urls or norm_title in seen_titles:
                continue
            seen_urls.add(norm_url)
            seen_titles.add(norm_title)
            merged.append(r)

    if tracker is not None:
        # 每个搜索方向算一次检索轮数
        tracker["search_rounds"] += len(queries)
        if success:
            tracker["tavily_success"] = True

    if not merged:
        return "Error: batch_search 未返回任何有效结果。"

    return _search_result_payload({"results": merged})
