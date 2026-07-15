import os
import asyncio

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import Matcher
from nonebot.rule import to_me

# 管理员 QQ 号白名单，逗号分隔，通过环境变量 ADMIN_USERS 配置
_admin_raw = os.getenv("ADMIN_USERS", "")
ADMIN_USERS: set[str] = {uid.strip() for uid in _admin_raw.split(",") if uid.strip()}

restart_cmd = on_command(
    "restart",
    rule=to_me(),
    aliases={"重启", "重启服务"},
    block=True,
    force_whitespace=True,
)


@restart_cmd.handle()
async def handle_restart(event: MessageEvent, matcher: Matcher):
    # 权限校验：只有白名单管理员能执行重启
    if ADMIN_USERS and str(event.user_id) not in ADMIN_USERS:
        await matcher.finish("你没有权限执行此操作")

    await matcher.send("正在重启...")
    # 给消息一点时间发出去，避免 os._exit 直接截断网络 IO
    await asyncio.sleep(0.5)
    os._exit(0)
