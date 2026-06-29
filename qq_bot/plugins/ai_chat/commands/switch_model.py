from nonebot import on_command
from nonebot import get_plugin_config
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent
from nonebot.matcher import Matcher
from nonebot.rule import to_me
from ..session_store import get_session_model, set_session_model
from ..config import AiChatConfig

AVAILABLE_ARGS = ["", "list", "deepseek-v4-flash", "deepseek-v4-pro", "gemini-3.5-flash"]

model_cmd = on_command(
    "model",
    rule=to_me(),
    aliases={"切换模型", "模型"},
    block=True,
    force_whitespace=True
)

@model_cmd.handle()
async def handle_model(event: MessageEvent, matcher: Matcher):
    config = get_plugin_config(AiChatConfig)

    if isinstance(event, GroupMessageEvent):
        session_id = f"group_{event.group_id}"
    else:
        session_id = f"user_{event.user_id}"

    arg = event.get_plaintext().strip().replace("/model", "").strip()
    if arg not in AVAILABLE_ARGS:
        return await matcher.finish(f"未知参数，可以使用/model查询更多信息")

    # /model 或 /model list →列出可用模型
    if arg == "" or arg == "list":
        current = get_session_model(session_id, config.ai_model)
        lines = ["可用模型："]
        for m in AVAILABLE_ARGS[2:]:
            mark = " ←当前" if m == current else ""
            lines.append(f"  {m}{mark}")
        lines.append(f"\n输入 /model <模型名> 切换")
        await matcher.finish("\n".join(lines))

    # /model <模型名> →切换
    if arg not in AVAILABLE_ARGS:
        await matcher.finish(
            f"没有这个模型。可选：{', '.join(AVAILABLE_ARGS)}"
        )

    set_session_model(session_id, arg)
    await matcher.finish(f"已切换到 {arg}")