import asyncio
import os
import time
from pathlib import Path

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import Matcher
from nonebot.rule import to_me

# 管理员 QQ 号白名单，逗号分隔，通过环境变量 ADMIN_USERS 配置
_admin_raw = os.getenv("ADMIN_USERS", "")
ADMIN_USERS: set[str] = {uid.strip() for uid in _admin_raw.split(",") if uid.strip()}


# nb run --reload 只监听 *.py / pyproject.toml 的文件变化来整进程重启，
# 因此重启不再用 os._exit(0)（那会导致重载器直接退出、无法自动拉起），
# 而是改写 reload_trigger.py 触发重载器重启。
class _ProjectRootNotFoundError(RuntimeError):
    """未找到 pyproject.toml，无法定位项目根目录。"""


def _project_root() -> Path:
    """向上查找项目根目录（含 pyproject.toml 的目录）。"""
    for directory in Path(__file__).resolve().parents:
        if (directory / "pyproject.toml").is_file():
            return directory
    raise _ProjectRootNotFoundError


_RELOAD_TRIGGER = _project_root() / "reload_trigger.py"

restart_cmd = on_command(
    "reboot",
    rule=to_me(),
    aliases={"重启", "重启服务"},
    block=True,
    force_whitespace=True,
)


def _touch_reload_trigger() -> None:
    """写入时间戳到 reload_trigger.py，触发 nb run --reload 整进程重启。"""
    _RELOAD_TRIGGER.write_text(
        f"# 由 /reboot 指令写入，用于触发热重载，请勿编辑。\n# {time.time()}\n",
        encoding="utf-8",
    )


@restart_cmd.handle()
async def handle_restart(event: MessageEvent, matcher: Matcher) -> None:
    # 权限校验：只有白名单管理员能执行重启
    if ADMIN_USERS and str(event.user_id) not in ADMIN_USERS:
        await matcher.finish("你没有权限执行此操作")

    await matcher.send("正在重启...")
    # 留出时间让消息发出去，再触碰触发文件，避免重启消息被截断
    await asyncio.sleep(0.5)
    _touch_reload_trigger()
