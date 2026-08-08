import json
from datetime import datetime
from typing import cast
from prompts.service import prompt_service
from .config import AiChatConfig
from ...ai.types import ChatMessage
from . import lifecycle
from . import token_usage
from .utils import split_message, extract_images, scan_and_save_members, get_group_members
from .memory_writing import get_memory
from .client_factory import get_client_for_model
from .long_term_memory import load_memory_for_context
from .session_store import _load_session_models, get_session_model
from .tools import TOOLS, get_tools_schema, current_scope, current_sender_name, current_search_tracker, SearchTracker

import nonebot
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, MessageSegment, Bot
from nonebot import get_plugin_config
from nonebot_plugin_localstore import get_plugin_data_dir


# 加载保存的谁使用什么模型的信息
_load_session_models()
# ──────── 主函数 ────────
async def handle_ai_chat(event: MessageEvent, matcher: Matcher):
    """主函数，接收用户消息解析处理发送给AI，然后解析回复用户AI的response"""
    # 用内存储存当前是对话状态的scope路径
    sender_name = event.sender.card or event.sender.nickname or "未知用户"
    # 获取bot对象，cast是typing中的用法，用来告诉语法检测器这个nonebot.get_bot()获取的对象类型一定是Bot
    bot = cast(Bot, nonebot.get_bot())

    if isinstance(event, GroupMessageEvent):
        scope = f"groups/{event.group_id}/{event.user_id}"
    else:
        scope = f"private/{event.user_id}"
    current_scope.set(scope)
    current_sender_name.set(sender_name)
    
    config = get_plugin_config(AiChatConfig)
    # 获取用户发送内容
    content = event.get_plaintext().strip()

    # 回复功能处理
    # hasattr用于检测event对象有没有'reply'属性
    if hasattr(event, 'reply') and event.reply:
        reply_data = getattr(event, 'reply', None)
        if reply_data:
            sender = reply_data.sender.card or reply_data.sender.nickname or "未知"
            raw = reply_data.raw_message
            if raw:
                content = f'[用户引用了 {sender} 的消息："{raw}"]\n{content}'
                print(repr(content))

    # 添加空内容回复规则
    if not content:
        # 通过函数获取路径，直接写死不够鲁棒/直接写路径一直报no such file错误，改用base64编码/错误原因写入的是字符串导致的格式识别错误，现在是通过python解析二进制文件直接传入
        sticker_path = get_plugin_data_dir() / "stickers" / "what.jpg"
        print("文件存在吗？", sticker_path.exists())
        img = MessageSegment.image(file=sticker_path.read_bytes())
        await matcher.finish(img)
        return

    # 区分私人对话和群聊对话
    if isinstance(event, GroupMessageEvent):
        session_id = f"group_{event.group_id}"
        is_group = True
    else:
        session_id = f"user_{event.user_id}"
        is_group = False

    # 获取必要参数
    model_name = get_session_model(session_id, config.ai_model)
    client = await get_client_for_model(config, model_name)
    memory = await get_memory(config)
    history = await memory.get_history(session_id)
    # 构建prompt
    memory_prompt = await load_memory_for_context()
    time_now = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
    system_part = prompt_service.get_system_prompt(current_time=time_now)
    # 多用户提示词注入
    if isinstance(event, GroupMessageEvent):
        member_info = get_group_members(event.group_id)
        if not member_info:
            success = await scan_and_save_members(bot, event)
            if success:
                member_info = get_group_members(event.group_id)
        # API 也失败时给兜底
        if not member_info:
            member_info = "暂无群成员信息"

        group_part = prompt_service.get_group_prompt(
            user_id=str(event.user_id),
            user_name=sender_name,
            member_info=member_info,
        )
    else:
        group_part = f"你当前正在与 {sender_name} 私聊。"
    # 多人用户个人长期记忆信息注入
    if memory_prompt:
        memory_part = f"以下是群聊中可见的长期记忆索引：{memory_prompt}"
    else:
        memory_part = ""
    # 拼接最终的prompt
    final_prompt = f"{group_part}\n\n{memory_part}\n\n{system_part}"
    messages= [ChatMessage(role="system", content=f"{final_prompt}")]
    # 直接将对话记录紧跟在prompt后面
    messages.extend(history)
    images = await extract_images(event)
    # 将图片信息传入messages中，让geminiclient中来处理
    identity_tag = f'<user identity id="{event.user_id}" name="{sender_name}"/>'
    messages.append(ChatMessage(role=f"user", content=f"{identity_tag}\n{content}", sender_name=sender_name, images=images or None))
    messages = memory.trim_if_needed(messages, config.max_context_tokens)
    # 加入工具调用处理
    search_agent_called = False  # 每次对话只允许调用一次 search_agent
    for _ in range(5):
        response = await client.chat(
            messages=messages,
            model = model_name,
            temperature = config.ai_temperature,
            max_tokens = config.ai_max_tokens,
            # 工具列表
            tools = get_tools_schema("search_agent","web_fetch", "save_memory", "cancel_reminder", "schedule_reminder", "query_chat_history")
        )
        # 记录本次调用的 token 消耗（失败请求内部自动跳过）
        await token_usage.record(
            response.prompt_tokens, response.cached_tokens, response.completion_tokens
        )
        # 如果没有工具调用就直接结束循环正常输出
        if not response.tool_calls:
            final_content = response.content or "AI暂时无法响应"
            break

        assistant_msg = ChatMessage(role="assistant", tool_calls=response.tool_calls, raw_parts=response.raw_parts)
        messages.append(assistant_msg)

        print(f"[INFO] 工具调用：{response.tool_calls}")
        for tc in response.tool_calls:
            func = tc["function"]
            # 构建工具调用
            tool = TOOLS[func["name"]]
            args = json.loads(func["arguments"])
            # 调用"search agent"工具的单独处理
            if func["name"] == "search_agent":
                if search_agent_called:
                    result = "[系统提示] 本轮对话已调用过搜索工具，请直接基于已有信息回答用户，不要再次搜索。"
                else:
                    search_agent_called = True
                    args = {"model": model_name, "task": args.get("task", content)}

                    tracker: SearchTracker = {"tavily_success": False, "tavily_error_count": 0}
                    current_search_tracker.set(tracker)
                    try:
                        await matcher.send(MessageSegment.text("正在找寻相关信息"))
                        result = await tool["func"](**args)
                    finally:
                        current_search_tracker.set(None)

                    # 子 Agent 全部轮次结束：若调用了 Tavily 但全程未返回有效结果，通知用户
                    if tracker["tavily_error_count"] > 0 and not tracker["tavily_success"]:
                        await matcher.send(
                            MessageSegment.text(f"⚠️ Tavily服务异常，检索过程失败{tracker['tavily_error_count']}次")
                        )
            else:
                result = await tool["func"](**args)

            print(f"[INFO] 工具响应：{result}")

            tool_res_msg = ChatMessage(
                role = "tool",
                content = result,
                tool_call_id = tc["id"],
            )
            messages.append(tool_res_msg)
    else:
        final_content = "AI暂时无法响应，请稍后重试"

    # 添加至记忆中
    sender_name = event.sender.card or event.sender.nickname or ""
    await memory.append(session_id, sender_name, content, final_content)

    if is_group:
        chunks = split_message(final_content)
        for idx, chunk in enumerate(chunks):
            if idx == 0:
                msg = MessageSegment.at(event.user_id) + MessageSegment.text("\n" + chunk)
            else:
                msg = MessageSegment.text(chunk)
            await matcher.send(msg)
        await matcher.finish()
    else:
        msg = MessageSegment.text(final_content)
    
    return await matcher.finish(msg)