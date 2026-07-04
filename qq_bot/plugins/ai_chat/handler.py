import json
from datetime import datetime
from .config import AiChatConfig
from ...ai.types import ChatMessage
from . import lifecycle
from .utils import spilt_message, extract_images
from .memory_writing import get_memory
from .client_factory import get_client_for_model
from .long_term_memory import load_memory_for_context
from .session_store import _load_session_models, get_session_model
from .tools import TOOLS, get_tools_schema,current_scope

from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, MessageSegment
from nonebot import get_plugin_config
from nonebot_plugin_localstore import get_plugin_data_dir


# 加载保存的谁使用什么模型的信息
_load_session_models()
# ──────── 主函数 ────────
async def handle_ai_chat(event: MessageEvent, matcher: Matcher):
    """主函数，接收用户消息解析处理发送给AI，然后解析回复用户AI的response"""
    # 用内存储存当前是对话状态的scope路径
    if isinstance(event, GroupMessageEvent):
        scope = f"groups/{event.group_id}/{event.user_id}"
    else:
        scope = f"private/{event.user_id}"
    current_scope.set(scope)
    
    config = get_plugin_config(AiChatConfig)
    content = event.get_plaintext().strip()
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
    system_prompt = config.system_prompt
    sender_name = event.sender.card or event.sender.nickname or "未知用户"
    # 多用户提示词注入
    if is_group:
        group_prompt = (
            f"""
            ### 最高优先级：多用户身份规则
            当前是群聊环境。
            聊天记录中的每一条消息都是独立用户发送的。

            每条消息都包含：
            - uid（唯一身份标识，不可混淆）
            - name（用户显示昵称，可重复）
            - content（消息内容）

            重要规则：
            1. uid 才是唯一身份标识
            2. 不允许混淆不同 uid 的身份
            3. 必须区分“谁说了什么”
            4. 不允许把不同用户的信息合并
            5. 不允许猜测用户身份

            ### 代词解析
            "我"
            永远表示当前消息对应的 name。
            "你"
            永远表示回复对象。
            "他"
            只能根据最近上下文确定。
            禁止将上一位发言人的"我"延续到下一位发言人。

            --------------------

            当前发言人 name:{sender_name}。
            """
        )
    else:
        group_prompt = f"\n\n你当前正在与 {sender_name} 私聊。"
    # 多人用户个人长期记忆信息注入
    if memory_prompt:
        long_term_mem_prompt = f"以下长期记忆仅属于当前发言人：{memory_prompt}"
    else:
        long_term_mem_prompt = ""
    # 拼接最终的prompt
    time_now = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
    system_prompt.replace("{current_time}", time_now)
    final_prompt = f"{group_prompt}\n\n{long_term_mem_prompt}\n\n{system_prompt}"
    messages= [ChatMessage(role="system", content=f"{final_prompt}")]
    # 直接将对话记录紧跟在prompt后面
    messages.extend(history)
    images = await extract_images(event)
    # 将图片信息传入messages中，让geminiclient中来处理
    messages.append(ChatMessage(role=f"user", content=f"[sending_time={time_now} uid={event.user_id} name={event.sender.card or event.sender.nickname}] {content}", sender_name=event.sender.card or event.sender.nickname, images=images or None))
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
            tools = get_tools_schema("search_agent","web_fetch", "save_memory", "cancel_reminder", "schedule_reminder")
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
            if func["name"] == "search_agent":
                if search_agent_called:
                    result = "[系统提示] 本轮对话已调用过搜索工具，请直接基于已有信息回答用户，不要再次搜索。"
                else:
                    search_agent_called = True
                    args = {"model": model_name, "task": args.get("task", content)}
                    await matcher.send(MessageSegment.text("正在搜索相关信息"))
                    result = await tool["func"](**args)
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
        final_content = "搜不到呢，你要不换个关键词试试"

    # 添加至记忆中
    sender_name = event.sender.card or event.sender.nickname or ""
    await memory.append(session_id, sender_name, content, final_content)

    if is_group:
        chunks = spilt_message(final_content)
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