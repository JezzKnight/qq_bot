from ..utils import scan_and_save_members
from ..config import AiChatConfig
from nonebot import get_plugin_config
from nonebot.rule import to_me
from nonebot import on_command
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent


scan = on_command("scan", rule=to_me(), aliases={"识别成员"}, block=True, force_whitespace=True)
@scan.handle()
async def scan_group_members(bot: Bot, event: GroupMessageEvent, matcher: Matcher):
    config = get_plugin_config(AiChatConfig)
    await scan_and_save_members(bot=bot, event=event, bot_self_id=config.bot_self_id)
    await matcher.finish("群成员信息扫描更新完毕")
    

    


