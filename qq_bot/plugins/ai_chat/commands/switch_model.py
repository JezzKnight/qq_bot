from nonebot import on_command
from nonebot import get_plugin_config
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent
from nonebot.matcher import Matcher
from nonebot.rule import to_me
from ..session_store import get_session_model, set_session_model
from ..config import AiChatConfig

# 未配置 AI_MODELS 注册表时的回退模型列表（保持旧行为）
LEGACY_ARGS = [
    "", "list",
    "glm-5.3-flash", "glm-5.3",
    "deepseek-v4-flash", "deepseek-v4-pro",
    "gemini-3.5-flash",
]

model_cmd = on_command(
    "model",
    rule=to_me(),
    aliases={"切换模型", "模型"},
    block=True,
    force_whitespace=True
)

def _available_names(config: AiChatConfig) -> list[str]:
    """可用模型名列表：优先取多模型注册表，否则回退硬编码列表"""
    if config.ai_models:
        return [m.name for m in config.ai_models]
    return LEGACY_ARGS[2:]


@model_cmd.handle()
async def handle_model(event: MessageEvent, matcher: Matcher):
    config = get_plugin_config(AiChatConfig)

    if isinstance(event, GroupMessageEvent):
        session_id = f"group_{event.group_id}"
    else:
        session_id = f"user_{event.user_id}"

    arg = event.get_plaintext().strip().replace("/model", "").strip()
    names = _available_names(config)

    # /model 或 /model list →列出可用模型
    if arg in {"", "list"}:
        current = get_session_model(session_id, config.ai_model)
        lines = ["可用模型："]
        for m in names:
            mark = " ←当前" if m == current else ""
            lines.append(f"  {m}{mark}")
        lines.append("\n输入 /model <模型名> 切换")
        await matcher.finish("\n".join(lines))

    # /model <模型名> →切换
    if arg not in names:
        await matcher.finish(f"没有这个模型。可选：{', '.join(names)}")

    set_session_model(session_id, arg)
    await matcher.finish(f"已切换到 {arg}")
