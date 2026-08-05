"""Tavily API 统一客户端 —— 封装多 key 轮换与故障切换。

设计要点:
- 所有 Tavily 调用（search / extract）共用同一套 HTTP 逻辑与 key 管理
- key 轮换基于内存状态 `_next_index`，记住上次成功的 key，避免重复撞限流
- 432/433（配额耗尽 / 限流）触发切换：跳过当前 key，用下一个 key 重试同一请求
- 网络超时与 key 无关，不触发切换
"""

import logging

import httpx
from nonebot import get_plugin_config

from qq_bot.plugins.ai_chat.config import AiChatConfig

logger = logging.getLogger(__name__)

# 命中即认为该 key 不可用，切换到下一个 key
# Tavily 错误码: 432 = 配额超限, 433 = 请求频率超限
KEY_SWITCH_STATUS_CODES = {432, 433}

_TAVILY_BASE_URL = "https://api.tavily.com"
_HEADERS = {"Content-Type": "application/json"}

# 下一个优先尝试的 key 下标（列表包装以便异步方法内赋值，进程内共享）
_next_index: list[int] = [0]


class TavilyClient:
    """Tavily 客户端，管理多 key 轮换"""

    def __init__(self) -> None:
        self._config = get_plugin_config(AiChatConfig)

    @property
    def _keys(self) -> list[str]:
        return list(self._config.Tavily_key)

    async def search(self, payload: dict) -> dict:
        """搜索接口"""
        return await self._request("/search", payload)

    async def extract(self, payload: dict) -> dict:
        """网页提取接口"""
        return await self._request("/extract", payload)

    async def _request(self, endpoint: str, payload: dict) -> dict:
        """核心请求逻辑：轮换 key，遇 432/433 切换重试"""
        keys = self._keys
        if not keys:
            print("Tavily_key 未配置，跳过请求")
            # logger.warning("Tavily_key 未配置，跳过请求")
            return {}

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0)
        ) as client:
            start = _next_index[0]
            for offset in range(len(keys)):
                idx = (start + offset) % len(keys)
                key = keys[idx]
                try:
                    response = await client.post(
                        url=f"{_TAVILY_BASE_URL}{endpoint}",
                        headers={**_HEADERS, "Authorization": f"Bearer {key}"},
                        json=payload,
                    )
                    print(f"[DEBUG] Tavily search 状态码: {response.status_code}")
                    print(f"[DEBUG] Tavily search 响应体: {response.text[:500]}")
                except httpx.ConnectTimeout:
                    # 网络问题，与 key 无关，直接失败
                    # logger.warning("网络异常，Tavily %s 连接超时", endpoint)
                    print("网络异常，Tavily %s 连接超时", endpoint)
                    return {}
                except httpx.HTTPError as e:
                    # logger.warning("Tavily %s 请求异常: %s", endpoint, e)
                    print("Tavily %s 请求异常: %s", endpoint, e)
                    return {}

                if response.status_code in KEY_SWITCH_STATUS_CODES:
                    # 该 key 配额/限流 → 永久跳过，换下一个重试
                    _next_index[0] = (idx + 1) % len(keys)
                    # logger.warning(
                    #     "Tavily key[%d] 返回 %d，切换到下一个 key",
                    #     idx, response.status_code,
                    # )
                    print(
                        "Tavily key[%d] 返回 %d，切换到下一个 key",
                        idx, response.status_code,
                    )
                    continue

                if not response.is_success:
                    # 其他错误（400/401/5xx 等），不视为 key 问题，直接失败
                    # logger.warning(
                    #     "Tavily %s 返回非预期状态码 %d: %s",
                    #     endpoint, response.status_code, response.text[:200],
                    # )
                    print(
                        "Tavily %s 返回非预期状态码 %d: %s",
                        endpoint, response.status_code, response.text[:200],
                    )
                    return {}

                # 成功 → 记住该 key，下次优先尝试
                _next_index[0] = idx
                # logger.info("Tavily %s 成功, 使用 key[%d]", endpoint, idx)
                print("Tavily %s 成功, 使用 key[%d]", endpoint, idx)
                return response.json()

        # 所有 key 均被限流/配额耗尽
        # logger.error("Tavily 所有 key 均不可用 (%d 个)", len(keys))
        print("Tavily 所有 key 均不可用 (%d 个)", len(keys))
        return {}
