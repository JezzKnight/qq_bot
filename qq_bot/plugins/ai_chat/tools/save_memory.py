import re
from .registry import register_tool
from .context import current_scope
from nonebot_plugin_localstore import get_plugin_data_dir
from pathlib import Path
from datetime import datetime

@register_tool(
    name="save_memory",
    description="将关于当前用户的重要信息保存为长期记忆。\n\n"
                "## 何时调用\n"
                "1. 用户告知了新的个人事实或偏好\n"
                "2. 用户的偏好发生了变化（如之前喜欢简短回复，现在说可以详细一点）\n"
                "3. 对话中产生了值得跨会话保留的知识\n\n"
                "## 更新已有记忆\n"
                "在保存前，先检查对话中已有的用户记忆索引（INDEX）。"
                "如果要保存的内容是对已有记忆的修正或补充，使用相同的 key 值，"
                "系统会自动覆盖更新。不要为同一事实创建不同 key。\n\n"
                "## 删除记忆\n"
                "如果用户明确表示某条记忆不再适用，key 填已有记忆的 key，"
                "content 填空字符串即可删除。",
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
                "description": "记忆正文。如要删除此记忆，填空字符串。"
            },
            "summary": {
                "type": "string",
                "description": "一行摘要，用于索引文件"
            },
            "scope": {
                  "type": "string",
                  "enum": ["personal", "group"],
                  "description": "记忆归属。personal=当前用户个人记忆（默认），group=群公共记忆（仅群聊可用）。"
            }
        },
        "required": ["key", "mem_type", "content", "summary"]},
)
async def save_memory(key: str, mem_type: str, content: str, summary: str, scope: str = "personal"):
    """储存长期记忆"""
    raw_scope = current_scope.get()
    root = get_plugin_data_dir() / "long_term_memory"
    if scope == "group" and raw_scope.startswith("groups/"):
        _, group_id, _ = raw_scope.split("/")
        scope_path = root / "groups" / group_id / "_group"
    else:
        scope_path = root / raw_scope

    mem_file = scope_path / f"{key}.md"
    # 删除功能
    if not content.strip():
        if mem_file.exists():
            mem_file.unlink()
    else:
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        created = now
        # 相同key覆盖
        if mem_file.exists():
            existing = parse_frontmatter(mem_file.read_text("utf-8"))
            created = existing.get("created", now)
        # 将字符串内容从f-string中剥离出来
        frontmatter = "\n".join([
            "---",
            f"name: {key}",
            f"description: {summary}",
            f"type: {mem_type}",
            f"created: {created}",
            f"updated: {now}",
            "---",
            "",
            content,
        ])
        scope_path.mkdir(parents=True, exist_ok=True)
        mem_file.write_text(frontmatter, encoding="UTF-8")

    rebuild_index(scope_path)
    return f"已保存记忆：{key}"


def parse_frontmatter(raw: str) -> dict:
      """通过正则匹配 解析 markdown 文件开头的 YAML frontmatter，解析.md文件中元数据中的内容然后返回dict"""
      match = re.match(r'^---\s*\n(.*?)\n---\s*\n', raw, re.DOTALL)
      if not match:
          return {}
      meta = {}
      for line in match.group(1).split("\n"):
          if ":" in line:
              k, v = line.split(":", 1)
              meta[k.strip()] = v.strip()
      return meta


def rebuild_index(scope_path: Path):
    """通过长期记忆文件夹中的文件来全量重构INDEX.md"""
    """
    INDEX.md 格式

    # Memory Index —user_123456
    最后更新: 2026-06-24T15:30:00

    ## Preferences
    - [用户偏好简短回复](prefers-short-reply.md) —不喜欢长篇，希望简洁

    ## Facts
    - [用户基本信息](basic-info.md) —名叫张三，在北京工作

    ## Knowledge
    - [AI Agent 开发](knowledge-ai-agent.md) —正在用 LangGraph 构建项目
    """
    scope_path.mkdir(parents=True,exist_ok=True)
    groups: dict[str, list[dict]] = {"fact": [], "preference": [], "knowledge": [], "note": []}
    # glob 方法，在 index_path 这个目录下匹配所有以 .md 结尾的文件。
    for md_file in sorted(scope_path.glob("*.md")):
        if md_file.name == "INDEX.md":
            continue

        raw = md_file.read_text(encoding="UTF-8")
        meta = parse_frontmatter(raw)
        if not meta:
            continue
        # 去 groups 这个字典里找刚才确定的类型。如果这个类型不存在，就先在字典里创建一个空列表 [] 作为它的值；如果存在，直接拿来用。
        groups.setdefault(meta.get("type", "note"), []).append({
              "name": meta.get("name", md_file.stem),
              "description": meta.get("description", ""),
        })
    # 组装 INDEX.md
    lines = [
        f"# Memory Index —{scope_path.parent.name}/{scope_path.name}",
        f"最后更新: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}",
        ""
    ]

    type_labels = {
        "fact": "## 事实 (Facts)",
        "preference": "## 偏好 (Preferences)",
        "knowledge": "## 知识 (Knowledge)",
        "note": "## 笔记 (Notes)",
    }
    # 通过记忆分类构建index
    for mem_type, label in type_labels.items():
        # 通过mem_type先去groups获取对应类型中储存的记忆列表
        items = groups.get(mem_type, [])
        if not items:
            continue
        lines.append(label)
        for item in items:
            lines.append(f"- [{item['name']}]({item['name']}.md) —{item['description']}")
        lines.append("")
    
    index_path = scope_path / "INDEX.md"
    index_path.write_text("\n".join(lines), encoding="UTF-8")
    


        
