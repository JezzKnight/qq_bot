# ruff: noqa: T201   # CLI 脚本用 print 输出迁移结果
"""长期记忆 .md → 单文件 JSON 一次性迁移脚本。

用法：在项目根目录运行 `python scripts/migrate_long_term_memory.py [--clean]`
- 默认：只生成新的 {scope}.json，旧 .md / INDEX.md / 用户子目录全部保留。
- --clean：迁移后再删除旧 .md / INDEX.md，用户子目录清空则一并删除。

旧数据在迁移前不会被改动，请先 review 生成结果再决定是否 --clean。
注意：迁移完成前，新版代码（只读 JSON）看不到旧记忆。
"""
import argparse
import json
import re
from pathlib import Path

import nonebot
from nonebot_plugin_localstore import get_data_dir

nonebot.init()

_DATA_ROOT = Path(get_data_dir("ai_chat")) / "long_term_memory"


def parse_frontmatter(raw: str) -> dict:
    """解析 md 开头 YAML frontmatter，返回 {key: value}。"""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
    if not match:
        return {}
    meta = {}
    for line in match.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta


def _parse_md_entry(md_file: Path) -> dict | None:
    """解析单个旧 .md 记忆文件 → 记忆条目；frontmatter 缺失或正文为空返回 None。"""
    raw = md_file.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n.*?\n---\s*\n", raw, re.DOTALL)
    if not match:
        return None
    body = raw[match.end() :].strip()
    if not body:
        return None
    meta = parse_frontmatter(raw)
    created = meta.get("created")
    return {
        "key": meta.get("name") or md_file.stem,
        "mem_type": meta.get("type", "note"),
        "content": body,
        "created": created,
        "updated": meta.get("updated") or created,
    }


def _load_existing(target: Path) -> dict[str, dict]:
    """读取目标 JSON 已有条目为 {key: entry}；缺失/损坏返回 {}。"""
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001  目标文件损坏时跳过合并
        print(
            f"[WARN] 目标 JSON 读取失败，跳过合并: {target}"
        )
        return {}
    entries: dict[str, dict] = {}
    raw_list = data.get("memories", []) if isinstance(data, dict) else []
    for m in raw_list:
        if isinstance(m, dict) and m.get("key"):
            entries[m["key"]] = m
    return entries


def migrate_dir_to_scope(scope: str, md_dir: Path, root: Path, *, clean: bool) -> int:
    """把一个旧 .md 目录聚合进 {root}/{scope}.json；返回迁移条数。

    目标 JSON 已存在时按 key 合并，保留 updated 较新的一方。
    """
    if not md_dir.is_dir():
        return 0
    target = root / f"{scope}.json"
    memories = _load_existing(target)

    converted = 0
    for md_file in sorted(md_dir.glob("*.md")):
        if md_file.name == "INDEX.md":
            continue
        entry = _parse_md_entry(md_file)
        if entry is None:
            continue
        old = memories.get(entry["key"])
        if old and old.get("updated", "") > entry["updated"]:
            continue
        memories[entry["key"]] = entry
        converted += 1

    if converted or target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"memories": list(memories.values())},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    if clean:
        for f in md_dir.glob("*.md"):
            f.unlink()
        if not any(md_dir.iterdir()):
            md_dir.rmdir()
    return converted


def main() -> None:
    parser = argparse.ArgumentParser(description="长期记忆 .md → 单文件 JSON 迁移")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="迁移后删除旧 .md/INDEX/用户子目录",
    )
    args = parser.parse_args()

    if not _DATA_ROOT.exists():
        print(f"长期记忆根目录不存在: {_DATA_ROOT}")
        return

    total = 0
    groups_root = _DATA_ROOT / "groups"
    if groups_root.exists():
        for gid_dir in sorted(p for p in groups_root.glob("*") if p.is_dir()):
            for sub in sorted(p for p in gid_dir.iterdir() if p.is_dir()):
                scope = f"groups/{gid_dir.name}/{sub.name}"
                n = migrate_dir_to_scope(scope, sub, _DATA_ROOT, clean=args.clean)
                if n:
                    print(f"{scope}: 迁移 {n} 条 → {scope}.json")
                total += n

    private_root = _DATA_ROOT / "private"
    if private_root.exists():
        for uid_dir in sorted(p for p in private_root.glob("*") if p.is_dir()):
            scope = f"private/{uid_dir.name}"
            n = migrate_dir_to_scope(scope, uid_dir, _DATA_ROOT, clean=args.clean)
            if n:
                print(f"{scope}: 迁移 {n} 条 → {scope}.json")
            total += n

    suffix = "旧 .md 文件已清理" if args.clean else "旧 .md 文件保留，可用 --clean 清理"
    print(f"完成，共迁移 {total} 条记忆。{suffix}。")


if __name__ == "__main__":
    main()
