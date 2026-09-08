import contextvars
from typing import Callable, Awaitable, TypedDict

# async def send(text: str) -> None 的回调签名
AsyncSender = Callable[[str], Awaitable[None]]


class SearchTracker(TypedDict):
    """子 Agent 搜索过程中累积的 Tavily 调用状态"""
    tavily_success: bool       # 至少一次返回了有效结果
    tavily_error_count: int    # 返回空/失败的次数
    search_rounds: int         # 累计检索轮数（每调用一次 web_search 加一）


class InteractionPayload(TypedDict):
    """委托式主动互动成功后的载荷：由 interact_with_member 工具写入、handler 收尾消费"""
    target_uid: str     # 目标成员 A 的 QQ 号
    opener_text: str    # @A 开场正文（不含 @、不含 id，由代码构造 @）


current_scope: contextvars.ContextVar[str] = contextvars.ContextVar("current_scope")
current_sender_name: contextvars.ContextVar[str] = contextvars.ContextVar("current_sender_name")
current_send_msg: contextvars.ContextVar[AsyncSender | None] = contextvars.ContextVar(
    "current_send_msg", default=None
)
current_search_tracker: contextvars.ContextVar[SearchTracker | None] = contextvars.ContextVar(
    "current_search_tracker", default=None
)
current_interaction: contextvars.ContextVar[InteractionPayload | None] = (
    contextvars.ContextVar("current_interaction", default=None)
)
