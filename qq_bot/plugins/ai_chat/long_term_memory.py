from .tools import current_scope
from nonebot_plugin_localstore import get_plugin_data_dir


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