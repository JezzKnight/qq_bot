from nonebot import on_message
from nonebot.rule import Rule, to_me
from nonebot.plugin import PluginMetadata
from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot import get_plugin_config
from .config import AiChatConfig
from .handler import handle_ai_chat
from .commands import clear_memory
from .commands import get_pixiv
from .commands import switch_model
from .commands import help
from .commands import scan_members
from .commands import list_reminders
from .commands import reboot

async def keyword_rule(event: Event) -> bool:
    """
    关键词触发实现
    """
    config = get_plugin_config(AiChatConfig)
    if not isinstance(event, MessageEvent):
        return False
    # 获取event传来的消息然后消除前后空格以及小写
    text = event.get_plaintext().strip().lower()
    # 循环配置里写的关键词然后当关键词在text中被提及的时候any返回True
    return any(kw.lower() in text for kw in config.trigger_keywords)

# nonebot中标准注册事件响应器
ai_chat = on_message(
    rule = to_me(),
    priority = 10,
    block = False,
)

@ai_chat.handle()
async def handle(event: MessageEvent, matcher: Matcher):
    await handle_ai_chat(event, matcher)


__plugin_meta__ = PluginMetadata(
    name="AI 对话",
    description="基于 OpenAI 兼容接口的 AI 对话插件",
    usage="@我 或 包含关键词的消息触发 AI 对话",
    config=AiChatConfig,
    supported_adapters={"~onebot.v11"},
)