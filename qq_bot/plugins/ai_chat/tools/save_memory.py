# ruff: noqa: E501   # 工具描述含大量中文示例，行宽超过 88 属有意为之
"""长期记忆保存工具：AI 将当前用户/群的稳定信息写入 per-scope JSON 单文件。

存储位置见 ../memory_store.py（long_term_memory/{scope}.json）。
"""
from qq_bot.plugins.ai_chat.memory_store import MemoryStore

from .context import current_scope
from .registry import register_tool


@register_tool(
    name="save_memory",
    description=(
        "将值得长期保留的信息保存为长期记忆（个人记忆或群公共记忆）。\n\n"
        "## 何时调用\n"
        "1. 用户告知了新的个人事实、偏好或长期特征\n"
        "2. 用户的偏好发生了变化，需要更新已有记忆\n"
        "3. 对话中出现了值得跨会话保留的稳定信息（人物长期特征、群内梗文化、群约定等）\n\n"
        "## scope 选择（群聊时必判，先定范围再保存）\n"
        "- 影响 bot 在群内对所有成员的行为/回复风格（如回复格式约定、群规、群内通用梗文化）→ scope='group'\n"
        "- 只关于当前发言者本人的身份/喜好/特征 → scope='personal'（默认）\n"
        "- 判断测试：这条信息成立后，bot 是否应对群里其他成员也照样执行？应该→group；仅对该成员本人→personal\n\n"
        "## 内容写作硬性要求（最重要）\n"
        "只保存【稳定、长期不变】的底层信息：\n"
        "- 禁止保存易变信息：QQ号/用户ID、机器人的名字、用户的群名片昵称、当前日期时间、临时状态、一次性事件\n"
        "- 用第三人称客观陈述，脱离本段对话上下文也能独立读懂\n"
        "- 禁止使用『他/她』等无明确指代的代词，禁止『用户说…』『之前…被推翻』这类对话过程描述\n"
        "- 涉及称呼时保存「用户希望被称呼为X」的偏好本身，而不是当前名片值\n\n"
        "## 更新与删除\n"
        "同一事实只用一个 key：修正/补充已有记忆时传相同 key 覆盖；"
        "用户明确表示某条记忆不再适用时，key 传原 key、content 填空字符串删除。\n\n"
        "## 示例\n"
        "✗ 用户ID 12345678   ✗ 群名片叫『问问AI本人』   ✗ 刚才他说了句好可爱\n"
        "✓ 喜欢假小子（长期偏好）   ✓ 有巨物恐惧症（稳定事实）   ✓ 要求被称呼为 god（身份偏好）"
    ),
    parameters={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "唯一标识（短横线连接）。更新已有记忆时使用相同 key，新建时创建新 key。如 'prefers-short-reply'"
            },
            "mem_type": {
                "type": "string",
                "enum": ["fact", "preference", "knowledge", "note"],
                "description": "记忆类型"
            },
            "content": {
                "type": "string",
                "description": "记忆正文（第三人称、稳定客观）。如要删除此记忆，填空字符串。"
            },
            "scope": {
                "type": "string",
                "enum": ["personal", "group"],
                "description": "记忆归属（默认 personal）。"
                                "personal=只关于当前发言者本人的事实/偏好，绑定该成员；"
                                "group=影响 bot 在群内对所有成员行为的约定（回复格式、群规、群通用梗），绑定整个群。"
                                "测试：该信息成立后 bot 是否应对群里其他成员也照样执行？是→group；仅对该成员→personal。"
            }
        },
        "required": ["key", "mem_type", "content"]},
)
async def save_memory(key: str, mem_type: str, content: str, scope: str = "personal") -> str:
    """储存长期记忆"""
    raw_scope = current_scope.get()
    if scope == "group" and raw_scope.startswith("groups/"):
        file_scope = f"groups/{raw_scope.split('/')[1]}/_group"
    else:
        file_scope = raw_scope
    return MemoryStore(file_scope).upsert(key, mem_type, content)
