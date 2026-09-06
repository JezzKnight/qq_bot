"""模型网关：唯一的模型解析入口，负责传输连接池与模型画像解析。

纯服务层，不依赖 NoneBot / pydantic——配置由插件层 client_factory 映射成
参数传入。能力画像合并顺序：注册表显式字段 → 内置默认表 → 名称/端点启发式。
"""

from dataclasses import dataclass

from .capabilities import ModelCapabilities
from .defaults import (
    default_capabilities_for,
    heuristic_capabilities_for,
    platform_for_host,
    provider_display_name,
)
from .openai_client import OpenaiCompatClient


@dataclass(frozen=True)
class ModelProfile:
    """某模型在网关层解析出的完整画像：归属平台 + 能力元数据。"""

    name: str
    platform: str
    provider_name: str
    capabilities: ModelCapabilities


class ModelGateway:
    """模型网关：按 (base_url, api_key) 复用 OpenAI 兼容传输连接池，并解析模型画像。"""

    def __init__(self) -> None:
        self._clients: dict[tuple[str, str], OpenaiCompatClient] = {}

    def get_client(
        self,
        base_url: str,
        api_key: str,
        default_model: str = "deepseek-chat",
    ) -> OpenaiCompatClient:
        """取（复用）某端点/密钥对应的 OpenAI 兼容客户端。

        default_model 只在调用方省略 ``model`` 参数时生效；连接池以
        (base_url, api_key) 为键，同一端点/密钥的模型共享同一 httpx 连接池。
        """
        key = (base_url, api_key)
        client = self._clients.get(key)
        if client is None:
            client = OpenaiCompatClient(
                base_url=base_url, api_key=api_key, default_model=default_model
            )
            self._clients[key] = client
        return client

    def get_profile(
        self,
        name: str,
        *,
        base_url: str,
        explicit: ModelCapabilities | None = None,
        platform: str | None = None,
    ) -> ModelProfile:
        """解析模型画像。

        explicit: 注册表显式能力字段（可空，覆盖内置默认表）
        platform: 平台标识（缺省按 base_url host 推断）
        """
        resolved_platform = (
            platform if platform is not None else platform_for_host(base_url)
        )
        capabilities = ModelCapabilities.overlay(
            explicit,
            default_capabilities_for(name),
            heuristic_capabilities_for(name, platform=resolved_platform),
        )
        return ModelProfile(
            name=name,
            platform=resolved_platform,
            provider_name=provider_display_name(resolved_platform),
            capabilities=capabilities,
        )

    async def close_all(self) -> None:
        """幂等关闭全部连接池并清空缓存（供生命周期 shutdown 调用）。"""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
