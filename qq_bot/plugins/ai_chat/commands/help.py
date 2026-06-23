from pathlib import Path
from nonebot import on_command
from nonebot import get_plugin_config
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, MessageSegment
from nonebot_plugin_localstore import get_plugin_data_dir
from nonebot.matcher import Matcher
from nonebot.rule import to_me
from ..config import AiChatConfig

COMMANDS = {
      "pixiv": {
          "args": "<类型>",
          "desc": "随机获取 Pixiv 排行榜图片",
          "aliases": ["图来", "来点色图"],
          "params": [
              {"name": "day",   "desc": "日榜（默认）",     "values": []},
              {"name": "week",  "desc": "周榜",             "values": []},
              {"name": "day_male", "desc": "男性向日榜",    "values": []},
              {"name": "week_original", "desc": "原创周榜", "values": []},
              {"name": "week_rookie", "desc": "新人日榜",   "values": []},
              {"name": "day_male_r18", "desc": "男性向R18", "values": []},
              {"name": "week_r18", "desc": "R18周榜",       "values": []},
          ],
      },
      "reset": {
          "args": "",
          "desc": "清除当前会话的 AI 记忆",
          "aliases": ["clear", "重置对话", "清除记忆"],
      },
      "help": {
          "args": "[指令名]",
          "desc": "显示帮助信息",
      },
  }

help_cmd = on_command("help", rule=to_me(), aliases={""}, block=True, force_whitespace=True)
@help_cmd.handle()
async def handle_help(event: MessageEvent, matcher: Matcher):
    arg = event.get_plaintext().strip().replace("/help", "").strip()
    if arg:
          # /help pixiv →单条详解
          info = COMMANDS.get(arg)
          if info:
              detail = [
                  f"/{arg} {info['args']}",
                  f"说明: {info['desc']}",
              ]
              if info.get("params"):
                  detail.append("\n参数说明:")
                  for p in info["params"]:
                      detail.append(f"{p['name']}: {p['desc']}")
              await matcher.finish("\n".join(detail))
          else:
              await matcher.finish(f"未知指令: {arg}")
    else:
          # /help →全部列表
          lines = ["可用指令，输入 /help <指令名> 查看详细用法:\n"]
          for name, info in COMMANDS.items():
              lines.append(f"/{name} —{info['desc']}")
          await matcher.finish("\n".join(lines))