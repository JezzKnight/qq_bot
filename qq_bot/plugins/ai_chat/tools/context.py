import contextvars
from typing import Callable, Awaitable, TypedDict

# async def send(text: str) -> None 的回调签名
AsyncSender = Callable[[str], Awaitable[None]]


class SearchTracker(TypedDict):
    """子 Agent 搜索过程中累积的 Tavily 调用状态"""
    tavily_success: bool       # 至少一次返回了有效结果
    tavily_error_count: int    # 返回空/失败的次数


current_scope: contextvars.ContextVar[str] = contextvars.ContextVar("current_scope")
current_sender_name: contextvars.ContextVar[str] = contextvars.ContextVar("current_sender_name")
current_send_msg: contextvars.ContextVar[AsyncSender | None] = contextvars.ContextVar(
    "current_send_msg", default=None
)
current_search_tracker: contextvars.ContextVar[SearchTracker | None] = contextvars.ContextVar(
    "current_search_tracker", default=None
)
