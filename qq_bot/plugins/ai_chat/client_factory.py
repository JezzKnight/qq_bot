"""将原先handler中搭建模型客户端的职责独立出来，并为其他模块单独提供客户端，这样所有利用这个模块客户端的部分共享连接池。

客户端以 (base_url, api_key) 为键缓存：多模型注册表（AI_MODELS）下不同模型
可能指向不同端点/密钥，切换模型时必须按配置创建/复用对应客户端，
不能用单一全局单例，否则切换后仍打到旧端点。
"""
from .config import AiChatConfig, ModelConfig
from ...ai.openai_client import Openaiclient
from ...ai.gemini_client import Geminiclient

_openai_clients: dict[tuple[str, str], Openaiclient] = {}
_gemini_clients: dict[tuple[str, str], Geminiclient] = {}
_vision_client: Openaiclient | None = None


def _resolve_model_entry(config: AiChatConfig, model: str) -> ModelConfig | None:
    """从多模型注册表查找模型配置；未命中返回 None（调用方回退 legacy 配置）"""
    for entry in config.ai_models:
        if entry.name == model:
            return entry
    return None


async def get_openai_client(
    config: AiChatConfig,
    base_url: str | None = None,
    api_key: str | None = None,
) -> Openaiclient:
    """获取 OpenAI 兼容客户端，按 (base_url, api_key) 复用连接池"""
    base_url = base_url or config.ai_base_url
    api_key = api_key or config.ai_api_key
    key = (base_url, api_key)
    if key not in _openai_clients:
        _openai_clients[key] = Openaiclient(base_url=base_url, api_key=api_key)
    return _openai_clients[key]


async def get_gemini_client(
    config: AiChatConfig,
    base_url: str | None = None,
    api_key: str | None = None,
) -> Geminiclient:
    """获取 Gemini 客户端，按 (base_url, api_key) 复用连接池"""
    base_url = base_url or "https://generativelanguage.googleapis.com/v1beta"
    api_key = api_key or config.gemini_api_key
    key = (base_url, api_key)
    if key not in _gemini_clients:
        _gemini_clients[key] = Geminiclient(base_url=base_url, api_key=api_key)
    return _gemini_clients[key]


async def get_vision_client(config: AiChatConfig) -> Openaiclient:
    """获取本地视觉模型客户端（复用 Openaiclient，独立连接池与独立配置）。

    视觉模型走本地 VL 服务，与主模型完全解耦；该客户端的调用不计入 token 统计。
    """
    global _vision_client
    if _vision_client is None:
        _vision_client = Openaiclient(
            base_url=config.vision_base_url,
            api_key=config.vision_api_key,
            default_model=config.vision_model,
        )
    return _vision_client


async def get_client_for_model(config: AiChatConfig, model: str):
    """按模型名选择客户端：优先从注册表解析 base_url/api_key，未命中回退 legacy 配置"""
    is_gemini = "gemini" in model.lower()
    entry = _resolve_model_entry(config, model)
    if entry is not None:
        base_url, api_key = entry.base_url, entry.api_key
        if is_gemini:
            return await get_gemini_client(config, base_url=base_url, api_key=api_key)
        return await get_openai_client(config, base_url=base_url, api_key=api_key)

    # legacy 回退：Gemini 走固定 Google 端点 + gemini_api_key；其余走主配置
    if is_gemini:
        return await get_gemini_client(config)
    return await get_openai_client(config)
