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
    tool_calls: list[dict] | None = None
    raw_parts: list[dict] | None = None