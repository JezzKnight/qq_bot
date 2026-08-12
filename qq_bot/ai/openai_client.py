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
        # trust_env=False：不读取系统环境代理（如 ZodAccess 等本地代理软件注入的 HTTP_PROXY）。
        # 若不关掉，发往本机 llama.cpp（127.0.0.1）的请求会被代理劫持，导致连接被重置 / 返回空响应。
        # 本客户端服务 DeepSeek 与本地模型，均需直连；Gemini 客户端保留代理（Google 在国内需代理才能访问）。
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0), trust_env=False)

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
                # 图片处理：如果有图片，将 content 转为 OpenAI vision 格式的 content parts 数组
                if m.images and m.role == "user":
                    import base64
                    content_parts: list[dict[str, Any]] = []
                    if m.content:
                        content_parts.append({"type": "text", "text": m.content})
                    for img in m.images:
                        b64 = base64.b64encode(img.data).decode("utf-8")
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{img.mine_type};base64,{b64}"
                            }
                        })
                    msg["content"] = content_parts
                else:
                    msg["content"] = m.content
            
            if m.tool_calls is not None:
                msg["tool_calls"] = m.tool_calls
            if m.tool_call_id is not None:
                msg["tool_call_id"] = m.tool_call_id
            if m.sender_name is not None:
                msg["name"] = m.sender_name
            # DeepSeek 思考模式：assistant 需原样回传 reasoning_content
            if m.role == "assistant" and m.reasoning_content is not None:
                msg["reasoning_content"] = m.reasoning_content
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
        # 提前定义对象类型
        last_error: Exception | None = None
        resp: httpx.Response | None = None
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
                        f"{type(e).__name__}: {e}，{wait}s 后重试..."
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
        # Pyright/Pylance 把 assert x is not None 当作类型收窄指令——在 assert 之后的代码里，x 被收窄为 Response
        assert resp is not None
        data = resp.json()

        print(f"data:{data}")
        # 服务商返回错误结构（{error: {...}}，如模型不支持图片输入/额度超限）而非正常 choices 时，
        # 优雅降级为可读消息返回给上层，避免 data["choices"] 抛 KeyError 导致整个会话崩溃
        if "choices" not in data or not data.get("choices"):
            error_info = data.get("error") or {}
            err_msg = error_info.get("message") or f"HTTP {resp.status_code}: {str(data)[:200]}"
            print(f"[ERROR] 模型服务返回错误: {err_msg}")
            return ChatResponse(content=f"模型返回错误：{err_msg}")

        usage = data.get("usage") or {}
        message = data["choices"][0]["message"]
        return ChatResponse(
            # 工具调用的话可能content为None所以改用.get来处理None
            content = message.get("content"),
            model = data["model"],
            finish_reason = data["choices"][0]["finish_reason"],
            prompt_tokens = usage.get("prompt_tokens", 0),
            completion_tokens = usage.get("completion_tokens", 0),
            # 输入缓存命中 token（DeepSeek/OpenAI 缓存机制）
            cached_tokens = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
            tool_calls = message.get("tool_calls"),
            # 思考模式推理内容，供多轮/工具调用时回传
            reasoning_content = message.get("reasoning_content"),
        )
        

    async def close(self):
        await self._client.aclose()
    
    
