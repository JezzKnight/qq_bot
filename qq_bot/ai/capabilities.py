"""模型能力元数据 schema。

能力字段统一用三态语义：
- ``None``  该来源未声明/未知（合并时被后续来源回填，或保持未知）
- ``False`` 明确不支持
- ``True``  明确支持

多来源合并见 :meth:`ModelCapabilities.overlay`：靠前来源的显式值覆盖靠后来源，
因此显式 ``False`` 能压过内置默认表里的 ``True``。合并顺序（model_gateway 中）：
注册表显式字段 → 内置默认表 → 名称/端点启发式。
"""

from dataclasses import dataclass
from typing import TypeVar

# 能力字段清单：ModelConfig 显式字段映射与合并都靠它，避免两处手写字段名失配
CAPABILITY_FIELDS: tuple[str, ...] = (
    "supports_vision",
    "supports_video",
    "supports_tools",
    "supports_reasoning",
    "context_window",
)

_T = TypeVar("_T")


def _pick(current: _T | None, nxt: _T | None) -> _T | None:
    """取第一个非 None：current 非空用 current，否则用 nxt（显式值覆盖默认值）。"""
    return current if current is not None else nxt


@dataclass(frozen=True)
class ModelCapabilities:
    """模型能力画像（全部可选，None = 未知）。

    supports_vision:    图片输入（OpenAI vision 格式 content parts / base64 data URI）
    supports_video:     通过 image_url.url 透传视频/公开媒体 URL
    supports_tools:     function calling（OpenAI 格式 tools）
    supports_reasoning: 思考模式（返回 reasoning_content 且需原样回传）
    context_window:     上下文窗口 token 数
    """

    supports_vision: bool | None = None
    supports_video: bool | None = None
    supports_tools: bool | None = None
    supports_reasoning: bool | None = None
    context_window: int | None = None

    @classmethod
    def overlay(cls, *layers: "ModelCapabilities | None") -> "ModelCapabilities":
        """逐字段取第一个非 None：靠前来源显式值覆盖靠后来源。

        注意不是"OR 合并"——显式 False 是有意义的值，必须压过默认 True。
        layers 全空时返回全未知画像。
        """
        result = cls()
        for layer in layers:
            if layer is None:
                continue
            result = cls(
                supports_vision=_pick(result.supports_vision, layer.supports_vision),
                supports_video=_pick(result.supports_video, layer.supports_video),
                supports_tools=_pick(result.supports_tools, layer.supports_tools),
                supports_reasoning=_pick(
                    result.supports_reasoning, layer.supports_reasoning
                ),
                context_window=_pick(result.context_window, layer.context_window),
            )
        return result
