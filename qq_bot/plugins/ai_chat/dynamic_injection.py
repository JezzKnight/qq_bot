"""进入模型前的动态长期记忆注入。

将旧的「全量注入全群成员记忆索引」替换为按当前消息动态注入：
  1. 群公共记忆（必注入）
  2. 当前发言者本人记忆（必注入）
  3. 术语库命中词义（可选，受 glossary_enabled 控制）
  4. 当前消息明确提及的成员记忆（人名匹配）

模块保持纯同步、显式参数、无 NoneBot 运行时依赖，便于 test/ 下直跑脚本验证。
"""
import re
from pathlib import Path

from nonebot_plugin_localstore import get_plugin_data_dir

from .glossary import GlossaryStore
from .utils import load_group_members_list


def _memory_root() -> Path:
    """长期记忆根目录；延迟计算，避免导入时依赖 NoneBot 插件注册。"""
    return get_plugin_data_dir() / "long_term_memory"


def _strip_frontmatter(raw: str) -> str:
    """剥离 md 开头 YAML frontmatter，返回正文；无 frontmatter 返回全文。"""
    match = re.match(r"^---\s*\n.*?\n---\s*\n", raw, re.DOTALL)
    return raw[match.end() :].strip() if match else raw.strip()


def _read_memory_entries(dir_path: Path) -> list[dict]:
    """读取某记忆目录下所有 .md（跳过 INDEX.md），返回 [{key, description, body}]。

    跳过 frontmatter 损坏、正文为空的文件；目录不存在返回空列表。
    """
    entries: list[dict] = []
    if not dir_path.is_dir():
        return entries
    for f in sorted(dir_path.glob("*.md")):
        if f.name == "INDEX.md":
            continue

        try:
            raw = f.read_text(encoding="utf-8")
        except OSError as e:
            print(f"[WARN] 读取记忆文件失败: {f} ({e})")
            continue

        body = _strip_frontmatter(raw)
        if not body:
            continue

        description = ""
        # 获取md文件中的YAML frontmatter，就是记忆文件中储存元数据的部分
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
        if m:
            for line in m.group(1).split("\n"):
                if line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()
                    break
        # f.stem (专门用于pathlib对象)获取去掉最后一个后缀的文件名
        entries.append({"key": f.stem, "description": description, "body": body})
    return entries


def _format_memory_block(header: str, entries: list[dict]) -> str:
    """格式化一组记忆：header + 每条 [key] description + 正文。"""
    lines = [header]
    for e in entries:
        lines.append(f"[{e['key']}] {e['description']}".rstrip())
        lines.append(e["body"])
    return "\n".join(lines)


def _identity_header(uid: str, name: str) -> str:
    """生成记忆块的用户身份标题。"""
    return f'## <user id="{uid}" name="{name}"/> 的个人记忆'


def _build_alias_map(members: list[dict] | None) -> dict[str, str]:
    """别名(小写) -> user_id。每个成员贡献 card、nickname 两个别名。"""
    alias_map: dict[str, str] = {}
    if not members:
        return alias_map
    for m in members:
        uid = str(m.get("user_id", ""))
        if not uid:
            continue
        for key in ("card", "nickname"):
            name = (m.get(key) or "").strip()
            if name:
                alias_map.setdefault(name.lower(), uid)
    return alias_map


def _build_name_map(members: list[dict] | None) -> dict[str, str]:
    """user_id -> 显示名（card 优先，nickname 兜底）。"""
    name_map: dict[str, str] = {}
    if not members:
        return name_map
    for m in members:
        uid = str(m.get("user_id", ""))
        if not uid:
            continue
        name_map[uid] = (m.get("card") or m.get("nickname") or "").strip()
    return name_map


def _alias_hit(alias: str, text_lower: str) -> bool:
    """短 ASCII 名（≤3 纯字母）要求词边界，避免 'god' 误伤 'godlike'；其余子串匹配。"""
    if len(alias) <= 3 and alias.isascii() and alias.isalpha():
        return re.search(
            rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text_lower
        ) is not None
    return alias in text_lower


def _match_member_entries(
    group_dir: Path,
    user_input: str,
    members: list[dict] | None,
    excluded: set[str],
) -> list[tuple[str, list[dict]]]:
    """人名匹配：返回 [(uid, 记忆条目)]，按别名长度降序；跳过 excluded 中的 uid。"""
    alias_map = _build_alias_map(members)
    text_lower = user_input.lower()
    seen_aliases: set[str] = set()
    matched_uids: set[str] = set()
    result: list[tuple[str, list[dict]]] = []
    for alias in sorted(alias_map, key=len, reverse=True):
        if alias in seen_aliases:
            continue
        uid = alias_map[alias]
        if uid in excluded or uid in matched_uids:
            continue
        if not _alias_hit(alias, text_lower):
            continue
        seen_aliases.add(alias)
        entries = _read_memory_entries(group_dir / uid)
        if entries:
            matched_uids.add(uid)
            result.append((uid, entries))
    return result


def _match_glossary(group_id: str, user_input: str, enabled: bool) -> str | None:
    """术语库命中注入块；未启用或空库时返回 None。"""
    if not enabled:
        return None
    try:
        terms = GlossaryStore(group_id).match(user_input)
    except Exception as e:
        print(f"[WARN] 术语库匹配失败，跳过术语注入: {e}")
        return None
    if not terms:
        return None
    return GlossaryStore.format_injection(terms)


def build_memory_injection(
    group_id: int | str,
    current_user_id: int | str,
    user_input: str,
    self_id: str | None = None,
    *,
    glossary_enabled: bool = True,
) -> tuple[str | None, list[str]]:
    """群聊动态记忆注入。

    返回 (注入文本, 命中的成员 user_id 列表，含当前发言者本人)。
    任何子步骤失败都降级跳过，不向调用方抛错。
    """
    gid = str(group_id)
    uid = str(current_user_id)
    group_dir = _memory_root() / "groups" / gid
    members = load_group_members_list(gid)
    name_map = _build_name_map(members)

    blocks: list[str] = []
    injected_uids: list[str] = []

    # 1. 群公共记忆（必注入）
    group_entries = _read_memory_entries(group_dir / "_group")
    if group_entries:
        blocks.append(_format_memory_block("## 群公共记忆", group_entries))

    # 2. 当前发言者本人记忆（必注入）
    self_entries = _read_memory_entries(group_dir / uid)
    if self_entries:
        blocks.append(
            _format_memory_block(
                _identity_header(uid, name_map.get(uid, "")), self_entries
            )
        )
        injected_uids.append(uid)

    # 3. 术语库命中（可选）
    glossary_block = _match_glossary(gid, user_input, glossary_enabled)
    if glossary_block:
        blocks.append(glossary_block)

    # 4. 人名匹配的他人记忆
    excluded = {uid}
    if self_id:
        excluded.add(str(self_id))
    for matched_uid, entries in _match_member_entries(
        group_dir, user_input, members, excluded
    ):
        blocks.append(
            _format_memory_block(
                _identity_header(matched_uid, name_map.get(matched_uid, "")), entries
            )
        )
        injected_uids.append(matched_uid)

    if not blocks:
        return None, injected_uids
    return "\n\n".join(blocks), injected_uids


def build_private_injection(user_id: int | str) -> str | None:
    """私聊：注入 long_term_memory/private/{user_id}/ 下本人全部记忆正文；无则 None。"""
    uid = str(user_id)
    entries = _read_memory_entries(_memory_root() / "private" / uid)
    if not entries:
        return None
    return _format_memory_block(f'## <user id="{uid}"/> 的个人记忆', entries)
