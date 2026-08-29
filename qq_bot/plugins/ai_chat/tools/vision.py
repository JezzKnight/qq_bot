"""视觉理解工具：通过本地部署的 VL 模型赋予 bot 图片理解能力。

图片分析统一走独立配置的本地视觉模型——复用 Openaiclient 客户端，
但单独配置 base_url/api_key/model，与主模型完全解耦；
该模型的 token 消耗不计入主模型的用量统计（不调用 token_usage.record）。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from nonebot import get_plugin_config

from prompts.service import prompt_service
from qq_bot.ai.types import ChatMessage, ImageData
from qq_bot.plugins.ai_chat.client_factory import get_vision_client
from qq_bot.plugins.ai_chat.config import AiChatConfig
from qq_bot.plugins.ai_chat.tools.registry import register_tool
from qq_bot.plugins.ai_chat.utils import download_image


@register_tool(
    name="image_understand",
    description=(
        "当用户发送了图片并询问与图片内容相关的问题时，调用此工具分析图片内容。"
        "你必须传入用户对图片的具体意图/问题，以及图片的URL列表。"
        "工具会调用本地视觉模型一次性分析全部图片并返回结果。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "description": "用户对图片的具体意图或问题，例如'这张图里有什么'。",
            },
            "urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "需要分析的图片URL列表，取自消息中注入的图片URL。",
            },
        },
        "required": ["intent", "urls"],
    },
)
async def image_understand(intent: str, urls: list[str]) -> str:
    """调用本地视觉模型分析图片，返回模型生成的内容作为工具响应。"""
    if not urls:
        return "Error: urls 不能为空。"

    config = get_plugin_config(AiChatConfig)
    if not config.vision_base_url or not config.vision_model:
        return "视觉模型未配置（vision_base_url / vision_model 为空），无法分析图片。"

    # 下载全部图片二进制（复用 extract_images 的下载逻辑）
    images: list[ImageData] = []
    for u in urls:
        img = await download_image(u)
        if img is not None:
            images.append(img)
    if not images:
        return "Error: 图片下载失败，无法分析。"

    system_prompt = prompt_service.get_agent_prompt(
        "vision",
        current_time = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y年%m月%d日 %H:%M:%S")
    )
    messages = [
        ChatMessage(role="system", content=system_prompt),
        # 图片走 images 字段，由 Openaiclient 转成 OpenAI vision 格式的 content parts
        ChatMessage(role="user", content=intent, images=images),
    ]

    client = await get_vision_client(config)
    # 一次请求携带全部图片，VL 模型可跨图对比；该模型用量不记录到 token 统计
    response = await client.chat(messages=messages, model=config.vision_model)
    return response.content or "图片分析失败，未能返回有效内容。"
