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
    out = _to_jpeg_bytes(img, quality=_JPEG_QUALITY)
    # 压缩后反而更大时退回原样
    if out and len(out) < len(data):
        return out, "image/jpeg"
    return data, mime


# 图片格式的权威判据是文件头魔数：既不是扩展名，也不该只信 HTTP content-type
# （服务端可能给 application/octet-stream 或干脆给错，见 note §72.2 / §75）
_MAGIC_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
)


def sniff_image_mime(data: bytes, *, fallback: str) -> str:
    """按文件头魔数判断图片真实格式，认不出时返回 fallback。

    为什么需要：向下游（视觉模型 / 图像编辑接口）声明图片格式时若声明错了，
    宽松的服务端会容忍，严格的会直接拒收——而"声明错但能跑"是最难排查的一类问题。
    """
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    for magic, mime in _MAGIC_PREFIXES:
        if data.startswith(magic):
            return mime
    return fallback


def _to_jpeg_bytes(img: object, *, quality: int) -> bytes:
    """透明/索引通道贴白底后转 RGB，编码为 JPEG 字节。

    供"发给视觉模型前的压缩"与"发给图像编辑接口前的尺寸约束"共用，
    两处对通道处理的语义必须一致（透明区贴白而不是变黑）。
    """
    from PIL import Image

    if img.mode in ("RGBA", "LA", "P"):  # type: ignore[attr-defined]
        if img.mode in ("LA", "P"):  # type: ignore[attr-defined]
            img = img.convert("RGBA")  # type: ignore[attr-defined]
        background = Image.new("RGB", img.size, (255, 255, 255))  # type: ignore[attr-defined]
        background.paste(img, mask=img.getchannel("A"))  # type: ignore[attr-defined]
        img = background
    else:
        img = img.convert("RGB")  # type: ignore[attr-defined]
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)  # type: ignore[attr-defined]
    return buf.getvalue()


# 图像编辑（图生图）的输入约束：官方建议宽高 384-2048、单图 ≤10MB。
# 与 shrink_image_for_vision 的区别：后者只在 >1.5MB 时才动手（为控制视觉编码耗时），
# 于是"体积小但长边 3000px"的图会带着超大边长进编辑接口——既拖慢生成，也偏离
# 官方推荐的清晰度区间。这里只要超过长边上限就缩放，且只缩不放。
_EDIT_MAX_SIDE = 2048
_EDIT_MAX_BYTES = 10 * 1024 * 1024
_EDIT_JPEG_QUALITY = 92


def clamp_for_image_edit(data: bytes, mime: str) -> tuple[bytes, str]:
    """把图片约束到图像编辑接口推荐的尺寸区间，返回 (新字节, 新 mime)。

    Pillow 缺失或解码失败时原样返回，交由服务端兜底
    （与 shrink_image_for_vision 采用同一降级策略）。
    """
    # 先按魔数校正声明格式：即使不改尺寸，也不能向下游声明错误的图片格式
    mime = sniff_image_mime(data, fallback=mime)
    try:
        from PIL import Image
    except ImportError:
        return data, mime
    try:
        img = Image.open(io.BytesIO(data))
    except (OSError, ValueError):
        return data, mime

    ratio = min(1.0, _EDIT_MAX_SIDE / max(img.size))
    if ratio >= 1.0 and len(data) <= _EDIT_MAX_BYTES:
        return data, mime
    if ratio < 1.0:
        img = img.resize(
            (max(1, round(img.width * ratio)), max(1, round(img.height * ratio))),
            Image.Resampling.LANCZOS,
        )
    out = _to_jpeg_bytes(img, quality=_EDIT_JPEG_QUALITY)
    # 缩过尺寸就一定用新结果；只为压字节且压不小时则退回原图
    if out and (ratio < 1.0 or len(out) < len(data)):
        return out, "image/jpeg"
    return data, mime
