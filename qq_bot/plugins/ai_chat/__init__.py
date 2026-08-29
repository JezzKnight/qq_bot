from nonebot import on_message
from nonebot.rule import Rule
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
from .commands import usage

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

async def at_me_rule(event: Event) -> bool:
    """任意位置 @机器人 即触发。

    适配器自带 to_me() 只检查消息首/尾段，@ 出现在中间（或尾部带非空白
    内容）时会漏触发导致静默不响应。此规则先沿用适配器原判定（私聊恒触发、
    首/尾 @、昵称唤起），再扫描消息全部段位兜底。
    """
    if not isinstance(event, MessageEvent):
        return False
    if event.is_tome():
        return True
    return any(
        seg.type == "at" and str(seg.data.get("qq", "")) == str(event.self_id)
        for seg in event.message
    )

# nonebot中标准注册事件响应器
ai_chat = on_message(
    rule = Rule(at_me_rule),
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