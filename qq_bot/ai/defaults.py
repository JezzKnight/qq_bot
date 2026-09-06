"""内置模型知识：精确名默认能力表、端点→平台推断、名称启发式兜底。

这里存放"不查网络也能确定"的模型事实，供 model_gateway 合并能力画像时使用。
优先级：注册表显式字段 > 本文件精确名表 > 名称启发式。
未实测的能力一律留 None，绝不臆造 True——宁可未知，不可让上层基于错误能力
断言去发图/发工具（例如把多模态提示词注入到一个实际上收不了图的模型）。
"""

from .capabilities import ModelCapabilities

# 平台标识：与注册表条目可选的 platform 字段、client_factory 共用同一套取值
PLATFORM_BIGMODEL = "bigmodel"
PLATFORM_DEEPSEEK = "deepseek"
PLATFORM_SILICONFLOW = "siliconflow"
PLATFORM_LOCAL = "local"
PLATFORM_OPENAI = "openai"

# 平台 → 展示名
_PLATFORM_PROVIDER: dict[str, str] = {
    PLATFORM_BIGMODEL: "智谱 BigModel (GLM)",
    PLATFORM_DEEPSEEK: "DeepSeek",
    PLATFORM_SILICONFLOW: "硅基流动 (SiliconFlow)",
    PLATFORM_LOCAL: "本地模型 (OpenAI 兼容)",
    PLATFORM_OPENAI: "OpenAI 兼容",
}

# host 关键字 → 平台（有序，首个命中的生效）
_PLATFORM_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("open.bigmodel.cn",), PLATFORM_BIGMODEL),
    (("api.deepseek.com",), PLATFORM_DEEPSEEK),
    (("siliconflow",), PLATFORM_SILICONFLOW),
    (("localhost", "127.0.0.1", "0.0.0.0"), PLATFORM_LOCAL),
)


def platform_for_host(base_url: str) -> str:
    """按 base_url 推断平台归属；未知端点归为 ``openai``。"""
    lower = base_url.lower()
    for keywords, platform in _PLATFORM_KEYWORDS:
        if any(k in lower for k in keywords):
            return platform
    return PLATFORM_OPENAI


def provider_display_name(platform: str) -> str:
    """平台 → 展示名；未知平台返回通用文案。"""
    return _PLATFORM_PROVIDER.get(platform, _PLATFORM_PROVIDER[PLATFORM_OPENAI])


# 精确名内置默认能力表。未收录的模型走 heuristic_capabilities_for 兜底。
# 依据（见 docs/note.md）：
# - glm-5.3-flash：vision 实测可收图 (#40)、OpenAI 兼容 + 思考模型 + 工具 (#38)
# - deepseek-v4-flash / -pro：纯文本，思考型 (#20/#24)
# - deepseek-v4-flash-vision-exp：vision + 视频 URL (#41)
_BUILTIN: dict[str, ModelCapabilities] = {
    # ── 智谱 BigModel (GLM) ──
    "glm-5.3-flash": ModelCapabilities(
        supports_vision=True, 
        supports_video=True,
        supports_tools=True, 
        supports_reasoning=True
    ),
    "glm-5.3": ModelCapabilities(
        supports_tools=True
    ),
    # ── DeepSeek ──
    "deepseek-v4-flash": ModelCapabilities(
        supports_vision=False,
        supports_video=False,
        supports_tools=True,
        supports_reasoning=True,
    ),
    "deepseek-v4-pro": ModelCapabilities(
        supports_vision=False,
        supports_video=False,
        supports_tools=True,
        supports_reasoning=True,
    ),
    "deepseek-v4-flash-vision-exp": ModelCapabilities(
        supports_vision=True,
        supports_video=True,
        supports_tools=True,
        supports_reasoning=True,
    ),
    "deepseek-chat": ModelCapabilities(
        supports_vision=False,
        supports_video=False,
        supports_tools=True,
        supports_reasoning=False,
    ),
    # reasoner 系列历史上不保证 function calling，tools 留未知
    "deepseek-reasoner": ModelCapabilities(
        supports_video=False, 
        supports_reasoning=True
    ),
    # ── 硅基流动 (SiliconFlow) 常见的路径形式型号 ──
    "deepseek-ai/DeepSeek-R1": ModelCapabilities(
        supports_video=False, 
        supports_reasoning=True
    ),
}


def default_capabilities_for(name: str) -> ModelCapabilities:
    """查精确名内置默认能力；未收录返回全未知画像。"""
    return _BUILTIN.get(name, ModelCapabilities())


def heuristic_capabilities_for(
    name: str, *, platform: str | None = None
) -> ModelCapabilities:
    """精确名表未收录时的启发式兜底。

    只做"正向加分"，绝不输出 False——防止把内置默认表里刻意声明的 False
    翻成错误值。命中则给出 True，未命中保持未知。
    """
    lower = name.lower()
    vision_tokens = ("vision", "vl", "vlm", "multimodal", "omni")
    supports_vision: bool | None = (
        True if any(t in lower for t in vision_tokens) else None
    )
    supports_video: bool | None = True if "video" in lower else None
    is_reasoning = any(t in lower for t in ("r1", "reasoner", "reasoning", "think"))
    supports_reasoning: bool | None = True if is_reasoning else None
    # DeepSeek / BigModel 官方端点普遍支持 function calling；
    # 思考专用型号（reasoner / R1 类）工具支持不保证，留给未知避免误判。
    supports_tools: bool | None = None
    if platform in (PLATFORM_DEEPSEEK, PLATFORM_BIGMODEL) and not is_reasoning:
        supports_tools = True
    return ModelCapabilities(
        supports_vision=supports_vision,
        supports_video=supports_video,
        supports_tools=supports_tools,
        supports_reasoning=supports_reasoning,
    )
