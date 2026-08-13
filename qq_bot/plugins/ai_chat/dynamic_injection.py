"""进入模型前的动态长期记忆注入。

将旧的「全量注入全群成员记忆索引」替换为按当前消息动态注入：
  1. 群公共记忆（必注入）
  2. 当前发言者本人记忆（必注入）
  3. 术语库命中词义（可选，受 glossary_enabled 控制）
  4. 当前消息明确提及的成员记忆（人名匹配）

模块保持纯同步、显式参数、无 NoneBot 运行时依赖，便于 test/ 下直跑脚本验证。
"""
import logging
import re

from .glossary import GlossaryStore
from .memory_store import MemoryStore
from .utils import load_group_members_list

logger = logging.getLogger(__name__)

_SHORT_ALIAS_MAX_LEN = 3  # 短 ASCII 名判定阈值，避免 'god' 误伤 'godlike'


def _read_memory_entries(scope: str) -> list[dict]:
    """读取某 scope 的全部长期记忆条目；文件缺失/损坏返回空列表。"""
    return MemoryStore(scope).load()


def _format_memory_block(header: str, entries: list[dict]) -> str:
    """格式化一组记忆：header + 每条 [key] content。"""
    lines = [header]
    lines.extend(
        f"[{e.get('key', '')}] {e.get('content', '')}".rstrip() for e in entries
    )
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
    """短 ASCII 名要求词边界，避免 'god' 误伤 'godlike'；其余子串匹配。"""
    if len(alias) <= _SHORT_ALIAS_MAX_LEN and alias.isascii() and alias.isalpha():
        return re.search(
            rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text_lower
        ) is not None
    return alias in text_lower


def _match_member_entries(
    gid: str,
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
        entries = _read_memory_entries(f"groups/{gid}/{uid}")
        if entries:
            matched_uids.add(uid)
            result.append((uid, entries))
    return result


def _match_glossary(group_id: str, user_input: str, *, enabled: bool) -> str | None:
    """术语库命中注入块；未启用或空库时返回 None。"""
    if not enabled:
        return None
    try:
        terms = GlossaryStore(group_id).match(user_input)
    except Exception:  # noqa: BLE001  术语库异常时跳过注入
        logger.warning("术语库匹配失败，跳过术语注入", exc_info=True)
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
    members = load_group_members_list(gid)
    name_map = _build_name_map(members)

    blocks: list[str] = []
    injected_uids: list[str] = []

    # 1. 群公共记忆（必注入）
    group_entries = _read_memory_entries(f"groups/{gid}/_group")
    if group_entries:
        blocks.append(_format_memory_block("## 群公共记忆", group_entries))

    # 2. 当前发言者本人记忆（必注入）
    self_entries = _read_memory_entries(f"groups/{gid}/{uid}")
    if self_entries:
        blocks.append(
            _format_memory_block(
                _identity_header(uid, name_map.get(uid, "")), self_entries
            )
        )
        injected_uids.append(uid)

    # 3. 术语库命中（可选）
    glossary_block = _match_glossary(gid, user_input, enabled=glossary_enabled)
    if glossary_block:
        blocks.append(glossary_block)

    # 4. 人名匹配的他人记忆
    excluded = {uid}
    if self_id:
        excluded.add(str(self_id))
    for matched_uid, entries in _match_member_entries(
        gid, user_input, members, excluded
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
    """私聊：注入 long_term_memory/private/{user_id}.json 本人全部记忆；无则 None。"""
    uid = str(user_id)
    entries = _read_memory_entries(f"private/{uid}")
    if not entries:
        return None
    return _format_memory_block(f'## <user id="{uid}"/> 的个人记忆', entries)
