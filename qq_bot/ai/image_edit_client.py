"""图像编辑传输层：DashScope「图像生成与编辑」同步接口。

**为什么不塞进 OpenaiCompatClient**（架构约束，见 docs/note.md §61.2 / §70.4）：
- 协议不同：本接口是 `input.messages[].content[]` 的图文交错结构 + `parameters`，
  与 chat/completions 无关；图像编辑也不该混进被主模型 / 子 Agent / 视觉工具
  共用的 chat 客户端。
- 出口策略不同：DashScope 是境内直连服务，必须 `trust_env=False`，否则 Windows 系统代理
  会劫持请求并把它拖到读超时（note §70 的真实事故）。

接口事实（一手文档，note §65.2 / §72 / §73）：
- 3.0 系列图生图支持 1-3 张输入图，图序由数组顺序定义；`content` 内**有且只有一个 text**
- 输出 PNG，URL **24 小时**有效 → 必须立刻下载成字节，不能把 URL 直接抛给上层
- `usage` 只给 `output_image_count` / `output_image_type`（1k/2k 计费档），**不给金额**
"""

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from .image_prep import clamp_for_image_edit
from .types import ImageData

logger = logging.getLogger(__name__)

_GENERATION_PATH = "/api/v1/services/aigc/multimodal-generation/generation"
_HTTP_OK = 200
# 产出图在 OSS 上，下载很快；给 60s 足够，且与生成请求的长超时分开
_DOWNLOAD_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
# 仅对"请求根本没送达"的连接层错误重试：读超时**绝不重试**
_CONNECT_RETRIES = 2


class ImageEditError(Exception):
    """图像编辑失败（配置缺失 / 接口报错 / 产出下载失败）。"""


@dataclass
class EditOutcome:
    """一次编辑调用的结果与可对账信息。"""

    images: list[ImageData]
    request_id: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


def _data_uri(img: ImageData) -> str:
    b64 = base64.b64encode(img.data).decode("ascii")
    return f"data:{img.mine_type};base64,{b64}"


def _extract_image_urls(body: dict[str, Any]) -> list[str]:
    """从同步响应里取出产出图 URL（output.choices[].message.content[].image）。"""
    choices = (body.get("output") or {}).get("choices") or []
    return [
        str(item["image"])
        for choice in choices
        for item in ((choice.get("message") or {}).get("content") or [])
        if item.get("image")
    ]


class ImageEditClient:
    """DashScope 图像生成与编辑（同步）客户端，独立连接池 + 独立出口策略。"""

    def __init__(  # noqa: PLR0913  传输层构造参数天然偏多，逐项来自配置
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 180.0,
        n: int = 1,
        size: str = "",
        prompt_extend: bool = True,
        enable_thinking: bool = False,
        negative_prompt: str = "",
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._n = n
        self._size = size
        self._prompt_extend = prompt_extend
        self._enable_thinking = enable_thinking
        self._negative_prompt = negative_prompt
        # trust_env=False：境内直连，无视系统代理（note §70）
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0), trust_env=False
        )

    async def edit(
        self,
        images: list[ImageData],
        instruction: str,
        *,
        size: str = "",
    ) -> EditOutcome:
        """执行一次图生图编辑。

        images 的顺序即"图一 / 图二…"，由调用方（工具层）固定为
        [被修改的原图, *参照图]，与 prompt 里的指代保持一致。
        """
        if not images:
            raise ImageEditError("没有可编辑的输入图片")
        if not instruction.strip():
            raise ImageEditError("编辑指令为空")

        content: list[dict[str, str]] = []
        for img in images:
            # 进接口前统一约束尺寸：官方建议宽高 384-2048，硬上限 10MB
            data, mime = clamp_for_image_edit(img.data, img.mine_type)
            content.append({"image": _data_uri(ImageData(data=data, mine_type=mime))})
        content.append({"text": instruction.strip()})

        parameters: dict[str, Any] = {
            "n": self._n,
            "prompt_extend": self._prompt_extend,
            "enable_thinking": self._enable_thinking,
            "watermark": False,
        }
        target_size = size or self._size
        if target_size:
            parameters["size"] = target_size
        if self._negative_prompt:
            parameters["negative_prompt"] = self._negative_prompt

        payload = {
            "model": self._model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }
        body = await self._post_json(payload)

        urls = _extract_image_urls(body)
        if not urls:
            raise ImageEditError("图像编辑服务未返回图片")
        out = [await self._download(url) for url in urls]
        return EditOutcome(
            images=out,
            request_id=str(body.get("request_id") or ""),
            usage=body.get("usage") or {},
        )

    async def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._base_url.rstrip("/") + _GENERATION_PATH
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        attempt = 0
        while True:
            try:
                resp = await self._client.post(url, headers=headers, json=payload)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                # 连接层失败 = 请求没送达，重试不会重复计费
                attempt += 1
                if attempt > _CONNECT_RETRIES:
                    raise ImageEditError(
                        f"连接图像编辑服务失败：{type(exc).__name__}"
                    ) from exc
                await asyncio.sleep(float(2 ** (attempt - 1)))
                continue
            except httpx.ReadTimeout as exc:
                # 读超时 = 服务端可能已经生成并计费，重试会重复扣费 → 明确不重试
                raise ImageEditError(
                    "图像编辑请求超时（服务端可能仍在生成；为避免重复计费不做重试）"
                ) from exc
            except httpx.HTTPError as exc:
                raise ImageEditError(
                    f"请求图像编辑服务失败：{type(exc).__name__}"
                ) from exc
            break
        return self._parse_response(resp)

    @staticmethod
    def _parse_response(resp: httpx.Response) -> dict[str, Any]:
        try:
            body = resp.json()
        except ValueError as exc:
            not_json = f"图像编辑服务返回了非 JSON 内容（HTTP {resp.status_code}）"
            raise ImageEditError(not_json) from exc
        error = body.get("error")
        if resp.status_code != _HTTP_OK or body.get("code") or error:
            detail = body.get("message")
            if not detail and isinstance(error, dict):
                detail = error.get("message")
            detail = detail or f"HTTP {resp.status_code}"
            failed = f"图像编辑失败：{detail}"
            raise ImageEditError(failed)
        return body

    async def _download(self, url: str) -> ImageData:
        try:
            resp = await self._client.get(
                url, follow_redirects=True, timeout=_DOWNLOAD_TIMEOUT
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ImageEditError(f"产出图下载失败：{type(exc).__name__}") from exc
        mime = resp.headers.get("content-type", "image/png").split(";")[0].strip()
        # 复用项目既有的 ImageData（mine_type 是历史拼写，保持一致以免多出类型）
        return ImageData(data=resp.content, mine_type=mime or "image/png")

    async def close(self) -> None:
        await self._client.aclose()
