from .registry import register_tool
from .context import current_scope
from nonebot_plugin_localstore import get_plugin_data_dir

@register_tool(
      name="recall_memory",
      description="读取当前用户的一条长期记忆的完整内容。当索引中的摘要不够详细时调用。",
      parameters={
          "type": "object",
          "properties": {
              "memory_names": {"type": "array", "items": {"type": "string"}, "description": "记忆文件名（不含 .md），如 ['prefers-short-reply']"}
          },
          "required": ["memory_names"]
      }
  )
async def recall_memory(memory_names):
    """读取多段具体的记忆内容"""
    scope = current_scope.get()
    
    lines = []
    for mem in memory_names:
        mem_file = get_plugin_data_dir() / "long_term_memory" / scope / f"{mem}.md"
        if mem_file.exists():
            lines.append(mem_file.read_text(encoding="utf-8"))
        else:
            print(f"[WARN] 尝试读取以下记忆失败，记忆不存在：{scope}/{mem}")

    return "\n\n".join(lines) if lines else "未匹配到任何相关记忆"