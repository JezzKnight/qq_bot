from nonebot import on_command
from nonebot import get_plugin_config
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent
from nonebot.matcher import Matcher
from nonebot.rule import to_me
from ..handler import get_memory
from ..config import AiChatConfig


reset = on_command("reset", rule=to_me(), aliases={"clear", "重置对话", "清除记忆"}, block=True, force_whitespace=True)

@reset.handle()
async def handle_reset(event: MessageEvent, matcher: Matcher):
    config = get_plugin_config(AiChatConfig)
    memory = await get_memory(config)

    if isinstance(event, GroupMessageEvent):
        session_id = f"group_{event.group_id}"
    else:
        session_id = f"user_{event.user_id}"

    memory.clear(session_id)
    await matcher.finish("对话记忆已清除")

