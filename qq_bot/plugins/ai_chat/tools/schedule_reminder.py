from datetime import datetime
from nonebot import get_plugin_config

from qq_bot.plugins.ai_chat.tools.registry import register_tool
from qq_bot.plugins.ai_chat.tools.context import current_scope
from qq_bot.plugins.ai_chat.config import AiChatConfig
from qq_bot.plugins.ai_chat.client_factory import get_client_for_model
from qq_bot.plugins.ai_chat.tools.registry import get_tools_schema, TOOLS
from qq_bot.agents.schedule_agent import ScheduleTaskAgent


async def _parse_user_intended_time(text:str) -> str | None:
    """将用户的口语时间表达解析为 ISO 8601

    这是整个功能最"脏"的部分——NLU 时间解析。
    策略：优先让 AI 在调用 tool 前自己算好，这里做二次校验。

    输入示例：
      "今晚12点"  → AI 应计算出 "2026-06-30T00:00:00"
      "明天下午3点" → AI 应计算出 "2026-06-30T15:00:00"
      "3小时后"    → AI 应计算出具体时间

    如果 AI 传了不可解析的格式，这里返回 None 并报错。
    """
    try:
        dt = datetime.fromisoformat(text)
        if dt <= datetime.now():
            return None
        return dt.isoformat()
    except (ValueError, TypeError):
        return None


async def build_scheduled_agent(prompt: str) -> ScheduleTaskAgent:
    """构造定时任务 Agent 触发时由 _fire_reminder 调用"""
    config = get_plugin_config(AiChatConfig)
    client = await get_client_for_model(config, config.ai_model)
    tools = get_tools_schema("search_agent", "query_chat_history")
    return ScheduleTaskAgent(
        client=client,
        tools=tools,
        model=config.ai_model,
        prompt=prompt,
        tool_registry=TOOLS,
    )


@register_tool(
    name="schedule_reminder",
    description=(
        "为用户创建定时任务，支持两种模式，由 task_type 区分：\n\n"
        "**reminder（简单提醒）**：到时间直接把 message 推送给用户。\n"
        "  适用：'提醒我睡觉''10分钟后提醒我开会'——只发通知，无需查询信息。\n"
        "  此时 message = 你要对用户说的完整文案。\n\n"
        "**agent_task（智能任务）**：到时间后你会被唤醒，需调用工具完成任务再回复。\n"
        "  适用：'明早8点查天气''今晚10点搜今天的新闻头条'——需要查询/搜索/分析。\n"
        "  此时 message = 给未来自己的任务指令，包含完整意图和约束条件。\n\n"
        "**判断标准**：需要调用工具获取信息的 → agent_task；只是发通知 → reminder。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "remind_at": {
                "type": "string",
                "description": (
                    "ISO 8601 格式的触发时间，精确到秒。"
                    "你必须根据当前时间和用户的自然语言表述自行计算。"
                    "参考当前时间: " + datetime.now().isoformat() + "\n"
                    "'今晚12点'→当天 00:00:00，'明天下午3点'→次日 15:00:00，"
                    "'30分钟后'→当前时间+30分钟。注意跨天和时区。"
                ),
            },
            "task_type": {
                "type": "string",
                "enum": ["reminder", "agent_task"],
                "description": (
                    "reminder：到点直接推送 message，不需要做任何查询。\n"
                    "agent_task：到点后你需要调用工具（天气/搜索等）完成任务。\n"
                    "判断依据：用户的要求是否涉及查询、搜索、获取实时信息或需要分析推理。"
                ),
            },
            "message": {
                "type": "string",
                "description": (
                    "根据 task_type 填写不同内容：\n\n"
                    "▸ reminder 模式 —— 你即将推送给用户的最终文案（第一人称视角）：\n"
                    "  ✓ '该睡觉了！已经凌晨了，早点休息吧 🌙'\n"
                    "  ✓ '会议还有5分钟开始，别忘了准备周报 📋'\n"
                    "  ✗ '提醒用户睡觉'（这是第三人称指令，不是推送文案）\n\n"
                    "▸ agent_task 模式 —— 你给未来自己的完整工作指令：\n"
                    "  ✓ '查询深圳今天天气，对比明天，给出穿衣和带伞建议'\n"
                    "  ✓ '搜索今天AI领域的头条新闻，用中文总结三条最重要的'\n"
                    "  ✗ '查天气'（太模糊，未来自己不知道要查哪里、输出什么）\n\n"
                    "关键：agent_task 的 message 保留用户完整意图和约束，"
                    "因为执行时没有对话上下文，全靠这一条指令。"
                ),
            },
        },
        "required": ["remind_at", "task_type", "message"],
    },
)
async def schedule_reminder_tool(remind_at: str, task_type: str, message: str = "") -> str:
    """AI调用的提醒创建工具"""
    # 延迟导入以打破与 scheduled_tasks 插件的循环依赖
    from ...scheduled_tasks.reminder_manager import create_reminder

    # 直接从current_scope中获取数据
    scope = current_scope.get()
    if scope is None:
        return "❌ 无法确定当前会话上下文，请稍后重试。"
    
    parts = scope.split("/")
    # 群聊与私聊的分开处理
    if parts[0] == "groups":
        target_type, target_id, creator = "group", parts[1], parts[2]
    else:
        target_type, target_id, creator = "private", parts[1], parts[1]
    # 校验时间
    parsed_time = await _parse_user_intended_time(remind_at)
    if parsed_time is None:
        return f"❌ 时间格式错误或已过期: {remind_at}。请使用 ISO 8601 格式（如 2026-06-30T00:00:00）。"
    # 创建提醒任务
    try:
        reminder = await create_reminder(
            remind_at=parsed_time,
            message=message,
            target_type=target_type,
            target_id=target_id,
            creator_user_id=creator,
            task_type=task_type,
        )
        msg = (
            f"✅ 提醒已设置！\n"
            f"⏰ 时间: {reminder.remind_at}\n"
            f"📝 内容: {reminder.message}\n"
            f"🔑 ID: {reminder.job_id}")
        print(msg)
        return msg
    except Exception as e:
        return f"❌ 提醒创建失败: {e}"
    
