from dataclasses import dataclass

@dataclass
class ImageData:
    data: bytes
    mine_type: str

@dataclass
class ChatMessage:
    role: str
    sender_name: str | None = None
    content: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None
    # DeepSeek 思考模式字段：多轮/工具调用时需原样回传给 API，否则被拒绝
    reasoning_content: str | None = None
    # 为gemini多模态准备的字段
    images: list[ImageData] | None = None
    raw_parts: list[dict] | None = None
    

@dataclass
class ChatResponse:
    content: str | None = None # 有工具调用时可能为空
    model: str | None = None
    finish_reason: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0 # 输入缓存命中 token
    tool_calls: list[dict] | None = None
    reasoning_content: str | None = None  # DeepSeek 思考模式的推理内容
    raw_parts: list[dict] | None = None