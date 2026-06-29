"""将原先handler中搭建模型客户端的职责独立出来，并为其他模块单独提供客户端，这样所有利用这个模块客户端的部分共享连接池"""
from .config import AiChatConfig
from ...ai.openai_client import Openaiclient
from ...ai.gemini_client import Geminiclient

_openai_client: Openaiclient | None = None
_gemini_client: Geminiclient | None = None

async def get_openai_client(config: AiChatConfig) -> Openaiclient:
    # 用_client全局对象来维持连接池，原先是每次调用都会创建一个新对象
    global _openai_client
    if _openai_client is None:
        _openai_client = Openaiclient(base_url=config.ai_base_url,
                    api_key=config.ai_api_key)
    return _openai_client
    # return Aiclient(base_url=config.ai_base_url,
    #                 api_key=config.ai_api_key)


async def get_gemini_client(config: AiChatConfig) -> Geminiclient:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = Geminiclient(api_key=config.gemini_api_key)
    return _gemini_client


async def get_client_for_model(config: AiChatConfig, model: str):
    """选择模型"""
    if "gemini" in model.lower():
        return await get_gemini_client(config)
    else:
        return await get_openai_client(config)