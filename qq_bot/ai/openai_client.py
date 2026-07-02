import httpx
import asyncio
from typing import Any
from .types import ChatMessage, ChatResponse

class Openaiclient:
    # httpx.AsyncClient构造函数是同步的，只创建对象不涉及IO
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.default_model = "deepseek-chat"
        # 在init中创建对象复用连接池
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))

    # **kwargs就是一个普通字典，操作方法与字典一致
    async def chat(self, messages: list[ChatMessage], model: str | None = None, tools = None, **kwargs) -> ChatResponse:
        """
        封装httpx通过post直接向模型供应商发请求，返回解析后的内容
        """
        headers = {"Authorization":f"Bearer {self.api_key}"}
        # API接口不接受null值，直接get获取没填就会得到null
        payload: dict[str, Any] =   {
            "model": model or self.default_model,
        }
        # 需要传入工具调用参数传给ai，解析传入的messages
        payload_messages: list[dict[str, Any]] = []
        for m in messages:
            msg: dict[str, Any] = {"role": m.role}
            if m.content is not None:
                msg["content"] = m.content
            if m.tool_calls is not None:
                msg["tool_calls"] = m.tool_calls
            if m.tool_call_id is not None:
                msg["tool_call_id"] = m.tool_call_id
            if m.sender_name is not None:
                msg["name"] = m.sender_name
            payload_messages.append(msg)
        payload["messages"] = payload_messages
        # 模型参数传入
        if "temperature" in kwargs:
            payload["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]
        # 工具改为由caller传入
        if tools:
            payload["tools"] = tools
        # 加入请求重试机制，最多尝试3次请求
        max_retries = 3
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = await self._client.post(
                    url=self.base_url,
                    headers=headers,
                    json=payload,
                )
                print(f"[INFO] 模型层openai_resp:{resp}")
                last_error = None
                break
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt  # 1s, 2s, 4s 指数退避
                    print(
                        f"[WARN] API 调用失败 (第{attempt + 1}/{max_retries}次): "
                        f"{type(e).__name__}，{wait}s 后重试..."
                    )
                    await asyncio.sleep(wait)

        if last_error is not None:
            print(f"[ERROR] API 调用失败 (已重试{max_retries}次): {type(last_error).__name__}: {last_error}")
            return ChatResponse(content="AI暂时无法响应，请稍后重试")
        """
        返回内容解析
        {
        'id': 'e381c2d8-aa9d-405a-af61-b4c51361d40d', 
        'object': 'chat.completion', 
        'created': 1779873438, 
        'model': 'deepseek-v4-flash', 
        'choices': [{
            'index': 0, 
            'message': {
                'role': 'assistant', 
                'content': '你好！我是一个友好的智能助手，旨在为你提供信息、解答问题并陪伴交流，随时乐意帮助你！', 
                'reasoning_content': '用户问好并需要一句话自我介绍。简单直接回应用户需求就好。我是智能助手，主要功能是提供信息解答和互动帮助。保持友好简洁，避免复杂表述。'}, 
                'tool_calls':[]
            'logprobs': None, 
            'finish_reason': 'stop'}], 
        'usage': {
            'prompt_tokens': 15, 
            'completion_tokens': 61, 
            'total_tokens': 76, 
            'prompt_tokens_details': {'cached_tokens': 0}, 
            'completion_tokens_details': {'reasoning_tokens': 38}, 
            'prompt_cache_hit_tokens': 0, 
            'prompt_cache_miss_tokens': 15}, 
        'system_fingerprint': 'fp_8b330d02d0_prod0820_fp8_kvcache_20260402'
        }
        """
        data = resp.json()
        print(f"data:{data}")
        return ChatResponse(
            # 工具调用的话可能content为None所以改用.get来处理None
            content = data["choices"][0]["message"].get("content"),
            model = data["model"],
            finish_reason = data["choices"][0]["finish_reason"],
            prompt_tokens = data["usage"]["prompt_tokens"],
            completion_tokens = data["usage"]["completion_tokens"],
            tool_calls = data["choices"][0]["message"].get("tool_calls")
        )
        

    async def close(self):
        await self._client.aclose()
    
    
