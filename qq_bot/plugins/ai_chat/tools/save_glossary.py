"""术语库保存工具：AI 在对话中遇到特殊词汇时调用，把词义存入当前群术语库。

存储位置与格式见 ../glossary.py（long_term_memory/groups/{group_id}/glossary.json）。
"""
from qq_bot.plugins.ai_chat.glossary import GlossaryStore

from .context import current_scope
from .registry import register_tool


@register_tool(
    name="save_glossary",
    description=(
        "将对话中出现的特定词汇（网络热梗、互联网黑话、特殊用语、生僻简称）"
        "及其含义保存到当前群的术语库。\n\n"
        "## 何时调用\n"
        "当对话中出现上述特定词汇，且你已确认或查到了它的准确含义时调用。"
        "保存后，后续对话中该词出现时系统会自动注入其含义，帮助理解。\n\n"
        "## 词义描述硬性要求\n"
        "definition 必须以第三人称客观视角描述该词汇的含义，"
        "只陈述该词在特定语境中的意思，"
        "不要代入任何主观成分（禁止添加个人评价如『我觉得』『这个很搞笑』，禁止揣测使用者意图）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "term": {
                "type": "string",
                "description": "该词汇本身，如 '我造密码'",
            },
            "definition": {
                "type": "string",
                "description": "该词汇的第三人称客观释义",
            },
        },
        "required": ["term", "definition"],
    },
)
async def save_glossary(term: str, definition: str) -> str:
    """保存术语释义到当前群的术语库"""
    scope = current_scope.get() or ""
    if not scope.startswith("groups/"):
        return "术语库仅支持群聊使用"
    group_id = scope.split("/")[1]
    GlossaryStore(group_id).add_term(term, definition)
    return f"已保存术语：{term}"
