import json
import httpx
from pathlib import Path
from .config import AiChatConfig
from ...ai.types import ChatMessage, ImageData
from ...ai.openai_client import Openaiclient
from ...ai.gemini_client import Geminiclient
from ...memory.manager import MemoryManager
from ...memory.sqlite_repo import SqliteRepository
from ...memory.repository import MemoryRepository
from .tools import TOOLS, get_tools_schema,current_scope
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, PrivateMessageEvent, MessageSegment
from nonebot import get_plugin_config,get_driver
from nonebot_plugin_localstore import get_plugin_data_dir


_openai_client: Openaiclient | None = None
_gemini_client: Geminiclient | None = None
_Memory: MemoryManager | None = None
# 用内存来记录群聊用的是什么模型
_session_models: dict[str, str] = {}
_models_file: Path | None = None
_driver = get_driver()


async def get_openai_client(config: AiChatConfig) -> Openaiclient:
    # 用_client全局对象来维持连接池，原先是每次调用都会创建一个新对象
    global _openai_client
    if _openai_client is None:
        _openai_client = Openaiclient(base_url=config.ai_base_url,
                    api_key=config.ai_api_key)
    return _openai_client
    # return Aiclient(base_url=config.ai_base_url,
    #                 api_key=config.ai_api_key)


async def get_gemini_client(config: AiChatConfig) -> Geminiclient:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = Geminiclient(api_key=config.gemini_api_key)
    return _gemini_client


async def get_memory(config: AiChatConfig) -> MemoryManager:
    """组装车间"""
    repo: MemoryRepository
    global _Memory
    if _Memory is not None:
        return _Memory

    if config.memory_backend == "sqlite":
        repo = SqliteRepository(db_path=Path(get_plugin_data_dir()) / "ai_chat" / "memory.db")
    else:
        raise ValueError(f"不支持的后端类型：{config.memory_backend}")
        
    await repo.init()
    _Memory = MemoryManager(repository=repo, max_history=config.max_history,)
    return _Memory


async def load_memory_for_context():
    """加载INDEX.md"""
    scope = current_scope.get()
    root = get_plugin_data_dir() / "long_term_memory"

    parts = []

    if scope.startswith("groups/"):
        # scope 格式: "groups/{group_id}/{user_id}"
        _, group_id, user_id = scope.split("/")

        # 1. 群公共记忆
        group_index = root / "groups" / group_id / "_group" / "INDEX.md"
        if group_index.exists():
            parts.append(group_index.read_text(encoding="utf-8"))

        # 2. 当前发言人的群内记忆
        user_index = root / scope / "INDEX.md"
        if user_index.exists():
            parts.append(user_index.read_text(encoding="utf-8"))
    else:
        # 私聊: "private/{user_id}"
        user_index = root / scope / "INDEX.md"
        if user_index.exists():
            parts.append(user_index.read_text(encoding="utf-8"))

    return "\n\n".join(parts) if parts else None


async def get_client_for_model(config: AiChatConfig, model: str):
    """选择模型"""
    if "gemini" in model.lower():
        return await get_gemini_client(config)
    else:
        return await get_openai_client(config)


def _get_models_file() -> Path:
      """和 MemoryManager 一样，数据放在插件 data 目录下"""
      return get_plugin_data_dir() / "ai_chat" / "session_models.json"


def _load_session_models():
    """模块加载时调用，从文件恢复"""
    global _session_models
    _models_file = _get_models_file()
    if _models_file.exists():
        try:
            _session_models = json.loads(_models_file.read_text(encoding="utf-8"))
        except Exception:
            _session_models = {}


def _save_session_models():
    """每次切模型时调用，写入文件"""
    global _models_file
    if _models_file is None:
        _models_file = _get_models_file()
    
    _models_file.parent.mkdir(parents=True, exist_ok=True)
    _models_file.write_text(
        json.dumps(_session_models, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def get_session_model(session_id: str, default_model: str) -> str:
      """获取当前会话使用的模型名，没有覆盖则用默认值"""
      return _session_models.get(session_id, default_model)


def set_session_model(session_id: str, model: str):
    """设置会话的模型覆盖（/model 命令调用）"""
    _session_models[session_id] = model
    _save_session_models()

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
        system_prompt += (
            f"\n\n你当前正在群聊中与 {sender_name} 对话。"
            f"\n在回复前你需要思考当前对话的是哪个用户，必须在思考的时候输出当前用户的名称，在识别对话记录的时候必须关注'name'字段来区分不同用户。"
            f"\n【重要】群聊中的每个用户是独立的个体。当前用户 {sender_name} 的偏好和其他用户无关。禁止将其他用户的偏好套用到 {sender_name} 身上。"
            f"\n回复前检查记忆索引（INDEX）：如果 INDEX 中没有 {sender_name} 的某项偏好，则视为该用户没有此偏好，按默认方式回复。"
        )
    else:
        system_prompt += f"\n\n你当前正在与 {sender_name} 私聊。"
    # 多人用户个人长期记忆信息注入
    if memory_prompt:
        system_prompt = f"{system_prompt}\n\n{memory_prompt}"
    messages= [ChatMessage(role="system", content=f"{system_prompt}")]
    # 直接将对话记录紧跟在prompt后面
    messages.extend(history)
    images = await extract_images(event)
    # 将图片信息传入messages中，让geminiclient中来处理
    messages.append(ChatMessage(role=f"user", content=content, sender_name=event.sender.card or event.sender.nickname, images=images or None))
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
            tools = get_tools_schema("search_agent","web_fetch", "save_memory", "recall_memory")
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
        # msg = MessageSegment.at(event.user_id) + MessageSegment.text(final_content)
        for i in spilt_message(final_content):
            await matcher.send(MessageSegment.text(i))
        await matcher.finish()
    else:
        msg = MessageSegment.text(final_content)
    return await matcher.finish(msg)

@_driver.on_shutdown
async def _cleanup():
    """退出时清理资源，结束生命周期"""
    global _Memory,_openai_client,_gemini_client
    if _Memory is not None:
        await _Memory.close()
    if _openai_client is not None:
        await _openai_client.close()
    if _gemini_client is not None:
        await _gemini_client.close()

# ──────── 特定功能函数 ────────
def spilt_message(text: str) -> list[str]:
    """切分回复消息，用于实现分段多发"""
    chunks = []
    for msg in text.split("\n\n"):
        if msg:
            chunks.append(msg)
        else:
            continue
    return chunks

async def extract_images(event: MessageEvent) -> list[ImageData]:
    images = []
    for i in event.get_message():
        if i.type == "image":
            img_url= i.data.get("url")
            if not img_url:
                continue
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                      resp = await client.get(img_url)
                      if resp.status_code == 200:
                          # 从响应头中获取类型
                          content_type = resp.headers.get("content-type", "image/jpeg")
                          images.append(ImageData(
                              data=resp.content,
                              mine_type=content_type
                          ))
            except Exception:
                print("[INFO] 图片下载失败")
                continue
    return images