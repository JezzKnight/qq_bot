import httpx
from ...ai.types import ImageData
from nonebot.adapters.onebot.v11 import MessageEvent

def spilt_message(text: str) -> list[str]:
    """切分回复消息，用于实现分段多发"""
    chunks = []
    for msg in text.split("\n\n"):
        if msg:
            chunks.append(msg)
        else:
            continue
    return chunks

async def extract_images(event: MessageEvent) -> list[ImageData]:
    """提取图片"""
    images = []
    for i in event.get_message():
        if i.type == "image":
            img_url= i.data.get("url")
            if not img_url:
                continue
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                      resp = await client.get(img_url)
                      if resp.status_code == 200:
                          # 从响应头中获取类型
                          content_type = resp.headers.get("content-type", "image/jpeg")
                          images.append(ImageData(
                              data=resp.content,
                              mine_type=content_type
                          ))
            except Exception:
                print("[INFO] 图片下载失败")
                continue
    return images