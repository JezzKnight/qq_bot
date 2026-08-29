import logging
import time

from nonebot import get_driver, get_plugin_config
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.drivers import Driver
from nonebot_plugin_localstore import get_plugin_data_dir

from . import client_factory, memory_writing, token_usage
from .config import AiChatConfig

logger = logging.getLogger(__name__)
_config = get_plugin_config(AiChatConfig)
_driver = get_driver()

# 上次发送启动通知的时间戳（使用列表包装以支持闭包内赋值）
_last_startup_notify: list[float] = [0.0]


@Driver.on_bot_connect
async def _on_bot_connect(bot: Bot):
    """WebSocket 连接后向指定群发送上线通知（带冷却期）"""
    group_id = _config.startup_notify_group
    if group_id == 0:
        return

    cooldown = _config.startup_notify_cooldown
    elapsed = time.time() - _last_startup_notify[0]
    if elapsed < cooldown:
        logger.info(
            "启动通知冷却中 (距上次 %.0fs, 冷却 %ds)", elapsed, cooldown
        )
        return

    try:
        # 先发文字
        await bot.send_group_msg(
            group_id=group_id,
            message="🐋 肥鲸 参上！",
        )
        # 再发图片
        image_path = get_plugin_data_dir() / "stickers" / "online.jpg"
        await bot.send_group_msg(
            group_id=group_id,
            message=Message(MessageSegment.image(file=image_path.read_bytes())),
        )
        _last_startup_notify[0] = time.time()
        logger.info("启动通知已发送 -> group:%d", group_id)
    except Exception:  # noqa: BLE001
        logger.warning("启动通知发送失败", exc_info=True)


@_driver.on_startup
async def startup() -> None:
    """启动时初始化资源"""
    await token_usage.init()


@_driver.on_shutdown
async def cleanup() -> None:
    """退出时清理资源"""
    if memory_writing._Memory is not None:
        await memory_writing._Memory.close()
    # 客户端按 (base_url, api_key) 缓存，逐个关闭所有连接池
    for client in client_factory._openai_clients.values():
        await client.close()
    for client in client_factory._gemini_clients.values():
        await client.close()
    if client_factory._vision_client is not None:
        await client_factory._vision_client.close()
    await token_usage.close()
