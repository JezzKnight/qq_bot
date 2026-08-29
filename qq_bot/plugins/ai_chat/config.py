from pydantic import BaseModel, Field, field_validator


class ModelConfig(BaseModel):
    """多模型注册表（AI_MODELS）中的单个模型配置"""

    name: str            # 模型名（/model 切换时使用的 key）
    base_url: str        # 该模型对应的服务端点
    api_key: str = ""    # 该模型对应的 API key


class AiChatConfig(BaseModel):
    # 继承自pydantic的基类，能够继承两个能力，一、能够自动进行类型校验 二、自动从环境变量读取配置
    ai_base_url: str
    ai_api_key: str = " "
    gemini_api_key: str = ""
    ai_model: str
    # 多模型注册表：/model 命令据此切换模型及其 base_url/api_key；
    # 未配置（空）时回退使用 ai_base_url/ai_api_key/gemini_api_key 的旧单模型行为
    ai_models: list[ModelConfig] = []
    ai_temperature: float = Field(default=1.0, ge=0.0, le=2.0, description="AI的temperature参数在[0,2]之间")
    ai_max_tokens: int = 16384

    # ── Bot 身份 ──
    # bot 自身 QQ 号：扫描群成员时排除自己；未配置时回退到 bot.self_id
    bot_self_id: str = ""

    @field_validator("bot_self_id", mode="before")
    @classmethod
    def parse_bot_self_id(cls, v: object) -> str:
        """QQ 号为纯数字，.env 中不加引号会被 NoneBot 解析成 int，统一转回 str"""
        if v is None:
            return ""
        return str(v)

    @field_validator("ai_models", mode="before")
    @classmethod
    def parse_ai_models(cls, v: object) -> object:
        """将 AI_MODELS（JSON 字符串）解析为 ModelConfig 列表；空值返回空列表"""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            import json
            return json.loads(v)  # pydantic 自动把 dict 列表强转为 ModelConfig
        return v

    # ── 本地视觉模型配置（复用 Openaiclient，但单独走本地 VL 服务）──
    vision_base_url: str = ""               # 本地视觉模型服务地址，空表示未启用
    vision_api_key: str = ""
    vision_model: str = ""

    # ── 记忆设置 ──
    memory_backend: str = "sqlite"
    max_history: int = 20                          # 最大历史消息条数
    max_context_tokens: int = 8192                 # 上下文总 token 上限

    # ── 动态记忆注入 ──
    memory_injection_enabled: bool = True      # 群聊动态注入总开关（False → 不注入长期记忆）
    glossary_enabled: bool = True              # 术语库注入开关（匹配命中时是否注入词义）

    # ── 触发设置 ──
    enable_at_trigger: bool = True                   # @ 触发开关
    enable_keyword_trigger: bool = False             # 关键词触发开关
    trigger_keywords: list[str] = ["bot", "机器人"]  # 触发关键词

    # ── 频率控制 ──
    cooldown_seconds: int = 5                       # 单用户冷却秒数
    max_daily_calls_per_user: int = 200             # 每人每天最大调用次数

    # ── 回复设置 ──
    reply_max_length: int = 1000                     # 单条消息最大字数

    # ── 启动通知 ──
    startup_notify_group: int = 0              # 启动通知目标群号，0 表示不发送
    startup_notify_cooldown: int = 300         # 启动通知冷却期（秒），防止频繁重启刷屏

    # ── Token 用量统计 ──
    token_usage_retention_days: int = 90       # 用量记录保留天数，<=0 表示永久保留

    # ── Pixiv访问控制 ──
    proxy: str = ""
    refresh_token: list[str] = []

    @field_validator("refresh_token", mode="before")
    @classmethod
    def parse_refresh_token(cls, v: str | list) -> list:
        """将环境变量中的 JSON 字符串解析为列表"""
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    # ── WebSearch配置 ──
    Tavily_key: list[str] = []

    @field_validator("Tavily_key", mode="before")
    @classmethod
    def parse_tavily_key(cls, v: str | list) -> list:
        """解析 Tavily key：支持 JSON 数组、逗号分隔、单值三种格式"""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("["):
                import json
                return json.loads(v)
            return [k.strip() for k in v.split(",") if k.strip()]
        return v
