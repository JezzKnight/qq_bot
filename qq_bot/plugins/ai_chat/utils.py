import httpx
import json
from ...ai.types import ImageData
import xml.etree.ElementTree as ET
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot_plugin_localstore import get_plugin_data_dir
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent


async def scan_and_save_members(bot: Bot, event: GroupMessageEvent, bot_self_id: str = ""):
    """获取并保存群成员信息（排除 bot 自身账号），成功返回 True，失败返回 False"""
    try:
        members = await bot.get_group_member_list(group_id=event.group_id)
    except Exception as e:
        print(f"[ERROR] 获取群成员列表失败: {e}")
        return False

    # 过滤掉 bot 自身：env 配置的 BOT_SELF_ID 优先，未配置时回退 bot.self_id
    exclude_id = bot_self_id.strip() or str(bot.self_id)
    if exclude_id:
        members = [
            m for m in members if str(m.get("user_id", "")) != exclude_id
        ]

    group_dir = get_plugin_data_dir() / "long_term_memory" / "groups" / str(event.group_id)
    if not group_dir.exists():
        group_dir.mkdir(parents=True, exist_ok=True)

    group_mem_file = group_dir / "members.json"
    group_mem_file.write_text(json.dumps(members, ensure_ascii=False), encoding='utf-8')
    return True


def load_group_members_list(group_id: int | str) -> list[dict] | None:
    """读取 members.json 原始 JSON 数组；文件缺失/损坏返回 None"""
    member_file = get_plugin_data_dir() / "long_term_memory" / "groups" / str(group_id) / "members.json"
    if not member_file.exists():
        return None
    try:
        return json.loads(member_file.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[WARN] 读取成员列表失败: {e}")
        return None


def get_group_members(group_id: int | str) -> str | None:
    """从本地文件获取群成员信息"""
    data = load_group_members_list(group_id)
    if not data:
        return None
    # 构造XML
    root = ET.Element("group_participants")

    for m in data:
        user = ET.SubElement(root, "user")
        user.set("id", str(m["user_id"]))

        # 优先使用群名片（card），若无则用昵称，最后用 user_id 兜底
        name = m.get("card") or m.get("nickname") or str(m["user_id"])
        user.set("name", name)

    # 返回格式化后的 XML 字符串（带缩进更美观）
    # 注意：ElementTree 默认输出没有缩进，下面的方式可添加缩进（Python 3.9+）
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", method="xml")


def split_message(text: str) -> list[str]:
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