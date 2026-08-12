from .registry import register_tool


@register_tool(
    name="save_digest",
    description="内部工具：检索流程必需前置步骤。"
                "发起 web_fetch 抓取网页前，必须先调用本工具提交检索进展摘要，"
                "并与 web_fetch 在同一次响应中一起调用（缺一不可）。"
                "作用：把已获得的搜索结果压缩为精炼摘要并替换原始结果，"
                "后续轮次不再重复读取原始搜索摘要（节省上下文）。"
                "摘要会完整保留全部关键事实与全部来源 URL，信息不丢失。",
    parameters={"type": "object",
                "properties": {
                "content":{
                    "type": "string",
                    "description": "压缩后的检索进展摘要：保留全部关键事实与来源 URL。"
                    }
                },
                "required": ["content"]
                }
)
async def save_digest(content: str) -> str:  # noqa: ARG001
    """此工具不会被真实执行：base.py 按名字拦截，仅捕获 content 做上下文替换。"""
    return "摘要已提交"
