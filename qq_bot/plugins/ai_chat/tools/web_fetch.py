import re
import uuid

from .context import current_search_tracker
from .registry import register_tool
from .tavily_client import TavilyClient

_client = TavilyClient()

# 网页正文中常见的图片类信息特征
_IMAGE_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")  # Markdown 图片 ![alt](url)
_IMAGE_LINK_RE = re.compile(  # 指向图片的 markdown 链接 [text](image_url)
    r"\[[^\]]*\]\([^)]*\.(?:png|jpe?g|gif|webp|svg|bmp|avif)[^)]*\)",
    re.IGNORECASE,
)
_IMAGE_HTML_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)  # HTML <img> 标签
_IMAGE_DATA_URI_RE = re.compile(  # data URI 图片
    r"data:image/[^,]+,[^\s)\]>\"']+",
    re.IGNORECASE,
)
_IMAGE_URL_RE = re.compile(  # 裸图片 URL
    r"https?://[^\s)\]>\"']+\.(?:png|jpe?g|gif|webp|svg|bmp|avif)"
    r"(?:\?[^\s)\]>\"']*|#[^\s)\]>\"']*)?",
    re.IGNORECASE,
)


def _filter_image_info(content: str) -> str:
    """剔除网页正文中的图片类信息，避免无意义的 token 消耗。"""
    content = _IMAGE_MD_RE.sub("", content)
    content = _IMAGE_LINK_RE.sub("", content)
    content = _IMAGE_HTML_RE.sub("", content)
    content = _IMAGE_DATA_URI_RE.sub("", content)
    return _IMAGE_URL_RE.sub("", content)


@register_tool(
    name="web_fetch",
    description=(
        "使用 Tavily 搜索引擎爬取网页的具体内容，"
        "当用户直接给出具体的网页网址时，使用该工具获取网页中的内容；"
        "当搜索摘要不足以回答问题时，也用该工具抓取相关网页的完整正文"
    ),
    parameters={
        "type": "object",
        "properties": {
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "爬取目标网页的具体urls列表，可以一次性爬取多个网站，"
                    "要求list格式，每个url是一个元素。"
                ),
            }
        },
        "required": ["urls"],
    },
)
async def web_fetch(urls: list[str]) -> str:
    tracker = current_search_tracker.get()
    # 每调用一次 web_fetch 也计入检索轮数
    if tracker is not None:
        tracker["search_rounds"] += 1

    payload = {
        # 决定搜索开销
        "urls": urls,  # 最多搜索结果zheg
        "extract_depth": "advanced",  # 搜索模式
    }

    results = await web_fetch_by_tavily(payload)
    if not results:
        return "Error: Tavily web fetcher does not return any results."
    return _fetch_result_payload(results)


async def web_fetch_by_tavily(payload: dict) -> dict:
    """tavily 爬取操作（统一走 TavilyClient 的 key 轮换）"""
    return await _client.extract(payload)


def _fetch_result_payload(data: dict) -> str:
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
            f"网页内容：{_filter_image_info(r['raw_content'])}\n\n"
        )

    return "\n\n".join(lines)
