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


# 链接噪音：URL 只耗 token 不携信息，链接文字保留（weather.com.cn 整页
# 实测 86% 字符是链接与 URL 噪音，是片段化回退时 prompt 膨胀的主因）。
# 支持一层嵌套括号，兼容 javascript:void(0)、sel("北京") 这类脚本地址。
_LINK_URL_PART = r"[^()]*(?:\([^()]*\)[^()]*)*"
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(" + _LINK_URL_PART + r"\)")
_BARE_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


def _strip_link_noise(content: str) -> str:
    """剔除网页正文中的链接噪音：[文字](链接) 只留文字，残余裸 URL 删除。"""
    content = _MD_LINK_RE.sub(lambda m: m.group(1), content)
    content = _BARE_URL_RE.sub("", content)
    content = re.sub(r"\n{3,}", "\n\n", content)  # 清洗后压缩连续空行
    return re.sub(r"[ \t]+\n", "\n", content)


def _clean_page_content(content: str) -> str:
    """网页正文清洗：先滤图片信息，再剔链接噪音。"""
    return _strip_link_noise(_filter_image_info(content))


@register_tool(
    name="web_fetch",
    description=(
        "使用 Tavily 搜索引擎爬取网页的具体内容，"
        "当用户直接给出具体的网页网址时，使用该工具获取网页中的内容；"
        "当搜索摘要不足以回答问题时，也用该工具抓取相关网页的关键片段。"
        "必须提供 query 说明本次想找什么，服务端按相关性只返回最相关的片段而非整页全文"
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
            },
            "query": {
                "type": "string",
                "description": (
                    "本次抓取想找的具体信息（用任务的核心关键词描述）。"
                    "服务端按相关性对内容片段 rerank，只返回与 query 最相关的部分。"
                ),
            },
        },
        "required": ["urls", "query"],
    },
)
async def web_fetch(urls: list[str], query: str) -> str:
    tracker = current_search_tracker.get()
    # 每调用一次 web_fetch 也计入检索轮数
    if tracker is not None:
        tracker["search_rounds"] += 1

    results = await web_fetch_by_tavily(_build_extract_payload(urls, query))
    if not results:
        return "Error: Tavily web fetcher does not return any results."
    return _fetch_result_payload(results)


# 每源返回的相关片段数上限（Tavily 允许 1-5，取上限给"完整表格/名单"类任务留余量）
CHUNKS_PER_SOURCE = 5


def _build_extract_payload(urls: list[str], query: str) -> dict:
    """构造 Tavily Extract 请求参数（片段模式）。

    query 触发服务端按相关性 rerank 的片段模式：每源最多 chunks_per_source 片、
    每片 500 字符以内，raw_content 不再回传整页全文——整页全文注入曾把末轮
    prompt 顶到 31k tokens（约 60s 生成），这是控制末轮体积的关键开关。
    """
    return {
        "urls": urls,
        "query": query,
        "chunks_per_source": CHUNKS_PER_SOURCE,
        "extract_depth": "advanced",  # 含表格与嵌入内容，时效数据类任务需要
    }


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
            f"网页内容：{_clean_page_content(r['raw_content'])}\n\n"
        )

    return "\n\n".join(lines)
