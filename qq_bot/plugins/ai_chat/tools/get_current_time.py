from .registry import register_tool
from datetime import datetime

@register_tool(
    name="get_current_time",
    description="获取当前的日期和时间",
    parameters={"type": "object",
                "properties": {},
                "required": []},
)
async def get_current_time() -> str:
    return datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")