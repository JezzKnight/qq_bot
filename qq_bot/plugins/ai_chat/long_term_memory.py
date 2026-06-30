from .tools import current_scope
from nonebot_plugin_localstore import get_plugin_data_dir


async def load_memory_for_context():
    """加载当前会话上下文中所有可见用户的长期记忆 INDEX"""
    scope = current_scope.get()
    root = get_plugin_data_dir() / "long_term_memory"

    parts = []

    if scope.startswith("groups/"):
        # scope 格式: "groups/{group_id}/{user_id}"
        _, group_id, current_user_id = scope.split("/")

        # 1. 群公共记忆
        group_index = root / "groups" / group_id / "_group" / "INDEX.md"
        if group_index.exists():
            parts.append(f"### 群公共记忆\n{group_index.read_text(encoding='utf-8')}")

        # 2. 扫描群内所有成员的记忆
        group_dir = root / "groups" / group_id
        if group_dir.exists():
            for user_dir in sorted(group_dir.iterdir()):
                if user_dir.name == "_group" or not user_dir.is_dir():
                    continue
                uid = user_dir.name
                user_index = user_dir / "INDEX.md"
                if not user_index.exists():
                    continue

                # 读取存储的显示名
                name_file = user_dir / "name.txt"
                display_name = ""
                if name_file.exists():
                    display_name = name_file.read_text(encoding="utf-8").strip()

                index_content = user_index.read_text(encoding="utf-8")

                if uid == current_user_id:
                    label = f"### <user id=\"{uid}\" name=\"{display_name}\"/> 当前发言人的个人记忆"
                else:
                    label = f"### <user id=\"{uid}\" name=\"{display_name}\"/> 的个人记忆"
                parts.append(f"{label}\n{index_content}")
    else:
        # 私聊: "private/{user_id}"
        user_index = root / scope / "INDEX.md"
        if user_index.exists():
            parts.append(user_index.read_text(encoding="utf-8"))

    return "\n\n".join(parts) if parts else None
