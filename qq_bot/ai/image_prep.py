"""图片预处理：发给视觉模型前压缩/缩放超限大图。

原因见 docs/note.md #48：超限大图的 base64 载荷过大，会让服务端视觉编码 +
思考模型生成远超过 180s 读超时（ReadTimeout），表现为"文本请求正常、图片请求
报错"。这里只处理超限图片，小图原样直传，避免无谓转码的画质损失与算力开销。

纯服务层，仅依赖 Pillow；Pillow 缺失或解码失败时静默退回原图，不影响主流程。
"""

import io

# 长边上限（px）：OpenAI 兼容视觉格式按 ~512px 分块计价/编码，1568 是性价比平衡点
_IMAGE_MAX_SIDE = 1568
# 超过此字节数才解码处理（小图直传）
_IMAGE_MAX_BYTES = 1_500_000
_JPEG_QUALITY = 90


def shrink_image_for_vision(data: bytes, mime: str) -> tuple[bytes, str]:
    """压缩/缩放超限图片，返回 (新字节, 新 mime)。

    长边超过 _IMAGE_MAX_SIDE 先缩放；透明通道贴白底后统一转 RGB 存 JPEG
    （尺寸不大但字节超限的高保真 PNG 也能借此压小）。结果不小于原字节数时退回原图。
    """
    if len(data) <= _IMAGE_MAX_BYTES:
        return data, mime
    try:
        from PIL import Image
    except ImportError:
        return data, mime
    try:
        img = Image.open(io.BytesIO(data))
    except (OSError, ValueError):
        # 非图片/损坏文件（PIL 解码失败），原样直传由模型端兜底
        return data, mime
    if max(img.size) > _IMAGE_MAX_SIDE:
        ratio = _IMAGE_MAX_SIDE / max(img.size)
        img = img.resize(
            (round(img.width * ratio), round(img.height * ratio)),
            Image.Resampling.LANCZOS,
        )
    if img.mode in ("RGBA", "LA", "P"):
        # 透明/索引通道贴到白底，避免变黑
        if img.mode in ("LA", "P"):
            img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.getchannel("A"))
        img = background
    else:
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    out = buf.getvalue()
    # 压缩后反而更大时退回原样
    if out and len(out) < len(data):
        return out, "image/jpeg"
    return data, mime
