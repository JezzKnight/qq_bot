import httpx
import json
import uuid
import asyncio
from typing import Any
from .types import ChatMessage, ChatResponse

class Geminiclient():
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    async def chat(self, messages: list[ChatMessage], model: str | None=None, tools = None, **kwargs):
        model_name = model or "gemini-3.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"

        payload = self._build_gemini_payload(messages = messages, tools = tools, **kwargs, )
        max_retries = 3
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = await self._client.post(url, json=payload)
                last_error = None
                break
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt  # 1s, 2s, 4s 指数退避
                    print(
                        f"[WARN] Gemini API 调用失败 (第{attempt + 1}/{max_retries}次): "
                        f"{type(e).__name__}，{wait}s 后重试..."
                    )
                    await asyncio.sleep(wait)

        if last_error is not None:
            print(f"[ERROR] Gemini API 调用失败 (已重试{max_retries}次): {type(last_error).__name__}: {last_error}")
            return ChatResponse(content="Gemini暂时无法响应，请稍后重试")

        return self._parse_response(resp.json())
    

    async def close(self):
        await self._client.aclose()


    def _build_gemini_payload(self, messages: list[ChatMessage], tools = None, **kwargs) -> dict:
        """
        构造gemini的请求体
        """
        payload = {}
        contents = []
        # ── 参数解析 ──
        for m in messages:
            if m.role == "system":
                payload["systemInstruction"] = {"parts": [{"text": f"{m.content}"}]}
            elif m.role == "user":
                parts = []
                # 加入图片处理，需要将文本和图片信息分开处理
                if m.content:
                    parts.append({"text": m.content})
                # 图片部分
                if m.images:
                    import base64
                    for img in m.images:
                        parts.append({
                            "inlineData":{
                                "mimeType": img.mine_type,
                                "data": base64.b64encode(img.data).decode("utf-8"),
                            }
                        })
                    
                contents.append({"role": "user", "parts": parts})
            elif m.role == "assistant":
                # 区分决定AI返回工具调用以及没有工具调用，工具调用分为有无content两种情况
                if m.tool_calls:
                    if m.raw_parts:
                        # 原样使用 Gemini 返回的 parts，不用重构
                        contents.append({"role": "model", "parts": m.raw_parts})
                    else:
                        # OpenAI 过来的，手动构造
                        parts = []
                        for tc in m.tool_calls:
                            parts.append({
                            "functionCall": {
                                "name": tc["function"]["name"],
                                "args": json.loads(tc["function"]["arguments"])
                            }
                        })
                        contents.append({"role": "model", "parts": parts})
                else:
                    # 没有工具调用，正常回复构造部分
                    contents.append({"role": "model", "parts": [{"text": f"{m.content}"}]})
            # 解析工具调用内容
            elif m.role == "tool":
                # 处理当tool_call_id为none的时候，类型检查器
                if not m.tool_call_id:
                    continue
                # 这里工具名要做反向解析因为传过来的是tool_call_id
                parts = m.tool_call_id.split("_")
                func_name = "_".join(parts[1:-1])
                contents.append({"role": "function", 
                                 "parts": [{
                                     "functionResponse": {
                                         "name": func_name, 
                                         "response": {"content": m.content}
                                         }
                                    }]
                                })
        
        payload["contents"] = contents
        # ── 工具定义 ──
        if tools:
            payload["tools"] = self._convert_tools(tools)
        # ── 生成参数 ──
        # 初始化generationConfig
        generation_Config = {}
        if "temperature" in kwargs:
            generation_Config["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            generation_Config["maxOutputTokens"] = kwargs["max_tokens"]
        if generation_Config:
            payload["generationConfig"] = generation_Config

        return payload


    def _parse_response(self, data: dict) -> ChatResponse:
        """
        返回内容解析
        {
        "candidates": [
            {
            "content": {
                "parts": [
                    {
                    "text": "你好！作为一名 Python 架构师，我非常推荐使用 `httpx`。相比传统的 `requests`，`httpx` 不仅支持完全兼容的同步 API，还原生支持**异步（async/await）**和 **HTTP/2**，这在高并发场景下非常有用。\n\n既然你想用 `httpx` 连接我（或者类似的大语言模型 API），我为你设计了两个原生的请求结构示例：**同步版本**和**异步版本**。\n\n这里我们以最常见的 **OpenAI 兼容接口规范** 为例。\n\n---\n\n### 1. 同步请求示例（适合脚本和简单任务）\n\n这是最基础的结构。我们使用 `httpx.Client()` 作为上下文管理器，这样可以复用 TCP 连接（Connection Pooling），提升性能。\n\n```python\nimport httpx\n\n# 1. 定义 API 配置\nBASE_URL = \"https://api.openai.com/v1\"  # 或者你使用的其他 LLM 服务商地址\nAPI_KEY = \"your-api-key-here\"\n\n# 2. 构建请求结构\nurl = f\"{BASE_URL}/chat/completions\"\nheaders = {\n    \"Authorization\": f\"Bearer {API_KEY}\",\n    \"Content-Type\": \"application/json\"\n}\npayload = {\n    \"model\": \"gpt-3.5-turbo\",  # 或其他模型名称\n",
                    "thoughtSignature": "11"
                    },
                    # 不一定有
                    {"functionCall": {
                        "name": "get_ship_stats",
                        "args": {"char_name": "企业"}
                    },
                ],  
                "role": "model"
            },
            "finishReason": "MAX_TOKENS",
            "index": 0
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 42,
            "candidatesTokenCount": 305,
            "totalTokenCount": 1038,
            "promptTokensDetails": [
                {
                    "modality": "TEXT",
                    "tokenCount": 42
                }
            ],
            "thoughtsTokenCount": 691,
            "serviceTier": "standard"
        },
        "modelVersion": "gemini-3.5-flash",
        "responseId": "aVElavCpHbDFjuMP8JbOuQY"
        }
        """
        print(f"Gemini返回内容：{data}")
        if not data.get("candidates"):
            block_reason = data.get("error", {}).get("message", "未知")
            return ChatResponse(content=f"内容被拦截，原因: {block_reason}")
        
        candidate = data["candidates"][0]
        content_obj = candidate.get("content", {})
        parts = content_obj.get("parts", [])

        # 检查 parts 里有没有 functionCall
        tool_calls = []
        text_parts = []
        extra_parts = []

        for p in parts:
            if "functionCall" in p:
                fc = p["functionCall"]
                tool_calls.append({
                    "id": f"call_{fc['name']}_{uuid.uuid4().hex[:6]}",            # ←Gemini 没 id，自己生成
                    "type": "function",
                    "function": {
                        "name": fc["name"],
                        "arguments": json.dumps(fc.get("args", {}), ensure_ascii=False),
                        # ↑Gemini args 是 dict →转成 JSON 字符串，对齐 OpenAI 格式
                    }
                })
            if "text" in p and "thought" not in p and "thoughtSignature" not in p:
                text_parts.append(p["text"])

        return ChatResponse(
            content="\n".join(text_parts) if text_parts else None,
            model=data.get("modelVersion", ""),
            finish_reason=candidate.get("finishReason", ""),
            prompt_tokens=data.get("usageMetadata", {}).get("promptTokenCount", 0),
            completion_tokens=data.get("usageMetadata", {}).get("candidatesTokenCount", 0),
            tool_calls=tool_calls if tool_calls else None,   # ←和 Aiclient 一样的格式
            raw_parts=parts if tool_calls else None
      )


    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """
        输入（OpenAI 格式）:
            [{"type":"function", "function":{name, description, parameters}}, ...]

        输出（Gemini 格式）:
            [{"functionDeclarations": [{name, description, parameters}, ...]}]
        """
        declarations = []
        for t in tools:
            # t["function"] = {name, description, parameters}
            declarations.append(t["function"])

        return [{"functionDeclarations": declarations}]