"""客户端工厂 → 模型网关的薄适配器。

本模块是 NoneBot 插件层与纯服务层 qq_bot/ai 网关之间的唯一桥梁：
把 AiChatConfig（pydantic/env）解析成网关所需参数，并持有全局 ModelGateway 单例。
调用方（handler / tools / agents）拿到的仍是带 .chat() 的 OpenAI 兼容客户端，
签名与旧版完全一致——模型层只有唯一的 OpenAI 兼容传输实现，无 Gemini 分支。
"""
from qq_bot.ai.capabilities import CAPABILITY_FIELDS, ModelCapabilities
from qq_bot.ai.image_edit_client import ImageEditClient
from qq_bot.ai.model_gateway import ModelGateway, ModelProfile
from qq_bot.ai.openai_client import OpenaiCompatClient

from .config import AiChatConfig, ModelConfig

# 全局网关：按 (base_url, api_key) 维护连接池 + 模型画像解析
_gateway = ModelGateway()


class _ImageEditState:
    """图像编辑客户端单例状态（避免 global 语句，同 token_usage 的写法）"""

    client: ImageEditClient | None = None
    signature: tuple[str, str, str] | None = None


_image_edit_state = _ImageEditState()


def _resolve_model_entry(config: AiChatConfig, model: str) -> ModelConfig | None:
    """从多模型注册表查找模型配置；未命中返回 None（调用方回退 legacy 配置）"""
    for entry in config.ai_models:
        if entry.name == model:
            return entry
    return None


def _to_explicit_capabilities(entry: ModelConfig | None) -> ModelCapabilities | None:
    """把注册表条目的可选能力字段映射为显式能力层。

    全部为空时返回 None，让网关走内置默认表而非空覆盖。
    """
    if entry is None:
        return None
    fields = {f: getattr(entry, f) for f in CAPABILITY_FIELDS}
    if all(v is None for v in fields.values()):
        return None
    return ModelCapabilities(**fields)


async def get_client_for_model(config: AiChatConfig, model: str) -> OpenaiCompatClient:
    """按模型名取（复用）OpenAI 兼容客户端。

    注册表命中用条目端点/密钥；未命中回退 legacy ai_base_url/ai_api_key。
    多模型注册表下不同模型可能指向不同端点/密钥，切换模型时必须按
    (base_url, api_key) 取对应客户端，不能用单一全局单例。
    """
    entry = _resolve_model_entry(config, model)
    if entry is not None:
        return _gateway.get_client(entry.base_url, entry.api_key)
    return _gateway.get_client(config.ai_base_url, config.ai_api_key)


async def get_vision_client(config: AiChatConfig) -> OpenaiCompatClient:
    """取本地视觉模型客户端（复用统一网关）。

    视觉模型走本地 VL 服务，独立 base_url/api_key/default_model 三件套，
    与主模型配置解耦；该客户端的调用不计入 token 统计。
    """
    return _gateway.get_client(
        config.vision_base_url,
        config.vision_api_key,
        default_model=config.vision_model,
    )


async def get_image_edit_client(config: AiChatConfig) -> ImageEditClient:
    """取图像编辑客户端（单例；关键配置变化时重建）。

    图像编辑是独立协议 + 独立出口策略（境内直连、trust_env=False），
    因此不复用 chat 连接池，单列一个客户端（见 note §61.2 / §70）。
    """
    signature = (
        config.image_edit_base_url,
        config.image_edit_api_key,
        config.image_edit_model,
    )
    state = _image_edit_state
    if state.client is not None and state.signature == signature:
        return state.client
    if state.client is not None:
        await state.client.close()
    state.client = ImageEditClient(
        base_url=config.image_edit_base_url,
        api_key=config.image_edit_api_key,
        model=config.image_edit_model,
        timeout=float(config.image_edit_timeout),
        n=config.image_edit_n,
        size=config.image_edit_size,
        prompt_extend=config.image_edit_prompt_extend,
        enable_thinking=config.image_edit_enable_thinking,
        negative_prompt=config.image_edit_negative_prompt,
    )
    state.signature = signature
    return state.client


def get_model_profile(config: AiChatConfig, model: str) -> ModelProfile:
    """解析模型画像（平台归属 + 能力元数据）。

    当前暂无调用方，作为网关的公共能力面落地——后续"多模态 system prompt 片段 /
    能力路由"直接按 capabilities.supports_vision / supports_video 判定即可。
    """
    entry = _resolve_model_entry(config, model)
    if entry is not None:
        return _gateway.get_profile(
            model,
            base_url=entry.base_url,
            explicit=_to_explicit_capabilities(entry),
            platform=entry.platform,
        )
    return _gateway.get_profile(model, base_url=config.ai_base_url)


async def close_all() -> None:
    """关闭全部模型连接池（生命周期 shutdown 调用，幂等）。"""
    await _gateway.close_all()
    if _image_edit_state.client is not None:
        await _image_edit_state.client.close()
        _image_edit_state.client = None
        _image_edit_state.signature = None
