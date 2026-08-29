# 🐋 qq_bot

基于 **NoneBot2 + OneBot V11** 的 QQ 群聊机器人。核心能力是与多模型 AI 对话（DeepSeek / 智谱 GLM / Gemini），并具备**工具调用、长期记忆、定时提醒、网页搜索**等增强能力。

---

## ✨ 功能特性

- **多模型 AI 对话**：通过 `/model` 在 `AI_MODELS` 注册的多个模型间切换，群聊支持多用户身份识别（`<user identity>` 标签），私聊/群聊共用一套对话引擎
- **工具调用（Function Calling）**：模型可在对话中自主调用搜索、记忆、提醒、图片理解等工具，最多 5 轮工具循环
- **长期记忆**：文件系统存储、按「群 × 用户」隔离；支持个人记忆 / 群共享记忆 / 私聊记忆，动态注入到提示词
- **会话历史**：SQLite 存储，按 token 估算自动裁剪
- **定时提醒**：AI 可通过 `schedule_reminder` 工具创建提醒，APScheduler 调度，重启后自动恢复未触发的任务
- **智能搜索**：`SearchAgent` 子代理多方向并行搜索 → 交叉验证 → 摘要压缩，支持 Tavily 搜索 + 网页抓取
- **图片/视频理解**：支持向支持视觉的多模态模型传图片或视频链接
- **Pixiv 榜单图**：`/pixiv` 随机获取日榜/周榜等排行榜图片
- **Token 用量统计**：`/usage` 查询每日消耗
- **热重载开发**：`nb run --reload`，改代码自动整进程重启；QQ 内 `/reboot` 远程重启

---

## 🧩 技术栈

| 类别 | 技术 |
|------|------|
| 框架 | NoneBot2 ≥ 2.5.0（FastAPI + WebSocket 驱动） |
| 协议 | OneBot V11 适配器 |
| AI 客户端 | 自研 OpenAI 兼容层 + Gemini 原生格式转换（`qq_bot/ai/`） |
| 存储 | SQLite（aiosqlite，WAL）+ 文件系统（长期记忆） |
| 调度 | APScheduler |
| 搜索 | Tavily API |
| 开发 | ruff（lint/format）、pyright（类型检查） |

---

## 📦 环境要求

- Python ≥ 3.10
- 一个 OneBot V11 协议端（如 [NapCat](https://github.com/NapNeko/NapCatQQ)、LLOneBot、Lagrange）作为 QQ 连接桥
- （可选）Tavily API Key、Pixiv refresh_token 用于对应功能

## 🚀 快速开始

```bash
# 1. 创建并激活虚拟环境
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. 安装依赖
pip install -e ".[dev]"

# 3. 配置 .env（参照下方「配置」一节填写）
#    也可直接复制项目根目录的 .env 模板后修改

# 4. 启动（带热重载）
nb run --reload
```

> 也可直接运行 `run_bot.bat`（Windows 本地脚本，已被 gitignore）。

### 热重载说明

- 修改任意 `*.py` 或 `pyproject.toml` 会自动**整进程重启**（nb-cli 监听文件变化）
- 修改 `.env` **不会**触发重载，需手动重启
- 进程崩溃不会自动拉起，需要重新运行 `nb run --reload`
- QQ 内对机器人说 `/reboot` 可触发一次重启（仅管理员白名单）

---

## ⚙️ 配置

项目使用 NoneBot 的 `.env` 文件 + `[tool.nonebot]`（pyproject.toml）加载配置。核心环境变量：

```bash
# ── 运行环境 ──
ENVIRONMENT=dev
DRIVER=~fastapi+~websockets
HOST=0.0.0.0
PORT=8080
ONEBOT_ACCESS_TOKEN=my_bot          # 与协议端一致

# ── 主模型（AI_MODELS 未配置时的回退）──
AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
AI_API_KEY=your_api_key
AI_MODEL=glm-5.3-flash

# ── 多模型注册表（/model 据此切换模型及其端点/Key，单行 JSON）──
AI_MODELS=[{"name":"glm-5.3-flash","base_url":"...","api_key":"..."},{"name":"deepseek-v4-flash","base_url":"...","api_key":"..."}]

# ── 身份与通知 ──
BOT_SELF_ID=12345678                # bot 自身 QQ 号
ADMIN_USERS=12345678                # 管理员白名单（/reboot 使用），逗号分隔
STARTUP_NOTIFY_GROUP=0              # 启动通知群号，0 关闭

# ── 可选功能 ──
TAVILY_KEY=your_tavily_key          # 网页搜索
REFRESH_TOKEN=your_pixiv_token      # Pixiv 榜单图
GEMINI_API_KEY=your_gemini_key      # Gemini 模型
```

其他可调配置见 [qq_bot/plugins/ai_chat/config.py](qq_bot/plugins/ai_chat/config.py)（如 `cooldown_seconds`、`max_context_tokens`、`reply_max_length`、`max_daily_calls_per_user`、`memory_injection_enabled` 等）。

---

## 💬 指令参考

指令需 `@机器人` 触发，带 `force_whitespace` 的指令在 `/` 后需加空格再接参数。

| 指令 | 别名 | 说明 |
|------|------|------|
| `/help [指令名]` | — | 查看帮助或单条指令详情 |
| `/model <模型名>` | `切换模型` | 切换当前会话使用的模型（`/model list` 查看可用项） |
| `/reset` | `clear` `重置对话` `清除记忆` | 清除当前会话的 AI 记忆 |
| `/pixiv <类型>` | `图来` | 随机获取 Pixiv 排行榜图片（day/week/day_male/week_rookie…） |
| `/reminders` | `提醒列表` `我的提醒` `定时任务列表` | 查看当前会话待执行的提醒 |
| `/usage [YYYY-MM-DD]` | `用量` `今日用量` | 查询 token 用量，默认今日 |
| `/scan` | `识别成员` | 扫描并保存群成员信息 |
| `/reboot` | `重启` `重启服务` | 整进程重启（仅 `ADMIN_USERS` 白名单） |

## 🤖 AI 工具能力

对话中模型可自主调用的工具（装饰器注册于 `qq_bot/plugins/ai_chat/tools/`）：

| 工具 | 说明 |
|------|------|
| `search_agent` | 多轮搜索子代理，限每轮对话调用 1 次 |
| `batch_search` | 一次性多方向并行搜索 + 摘要压缩 |
| `web_search` / `web_fetch` | Tavily 搜索与网页抓取 |
| `save_memory` / `recall_memory` | 长期记忆写入与按需查询 |
| `save_glossary` / `save_digest` | 术语库与对话摘要 |
| `query_chat_history` | 查询会话历史 |
| `schedule_reminder` / `cancel_reminder` | 创建 / 取消定时提醒 |
| `image_understand` | 图片理解（本地 VL 模型或主模型视觉能力） |

## 🧠 记忆系统

- **会话历史**：`MemoryManager` + SQLite 仓库，按 `max_context_tokens` 估算裁剪旧消息
- **长期记忆**：文件系统，路径按 `groups/{群}/{用户}`、`groups/{群}/_group`、`private/{用户}` 隔离
- **动态注入**：开启 `MEMORY_INJECTION_ENABLED` 时，相关长期记忆与术语在每次对话前注入提示词

---

## 📁 项目结构

```
qq_bot/
├── bot.py                      # （已废弃删除，改用 nb run --reload）
├── pyproject.toml              # [tool.nonebot] 插件/适配器声明 + ruff/pyright 配置
├── qq_bot/
│   ├── ai/                     # AI 客户端层（OpenAI 兼容 + Gemini 转换）
│   ├── agents/                 # 子代理系统（SearchAgent、ScheduleTaskAgent）
│   ├── memory/                 # 记忆基础设施（SQLite 会话历史）
│   └── plugins/
│       ├── ai_chat/            # 核心 AI 对话插件（指令、工具、记忆、会话管理）
│       └── scheduled_tasks/    # 定时提醒插件（APScheduler + 提醒仓库）
├── prompts/                    # 提示词模板（人设/能力/约束/风格/agents）
├── data/                       # 运行数据（数据库、记忆、本地存储，gitignore）
└── docs/                       # 知识库与技术决策记录
```

---

## 🛠️ 开发

```bash
ruff check .        # 代码规范检查
ruff format .       # 代码格式化
pyright            # 类型检查
```

> 提交前请确保 `ruff check .` 通过（`pyproject.toml` 启用了大量严格规则）。

## 📄 文档

- 技术架构与知识库：见 [docs/](docs/)（架构、路线图、问题记录 `note.md`）
- NoneBot2 文档：https://nonebot.dev/
