import httpx
import random
import json
from datetime import datetime, timedelta
from pathlib import Path
from nonebot import on_command
from nonebot import get_plugin_config
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, MessageSegment
from nonebot_plugin_localstore import get_plugin_data_dir
from nonebot.matcher import Matcher
from nonebot.rule import to_me
from .cooldown import check_cooldown
from ..config import AiChatConfig

ALLOWED_MODES = {"", "day", "week", "month", "day_male", "day_female", "week_origin", "week_rookie", "day_r18", "day_female_r18", "week_r18"}

pixiv = on_command("pixiv", rule=to_me(), aliases={"图来", "来点色图"}, block=True, force_whitespace=True)
@pixiv.handle()
async def handle_pixiv(event: MessageEvent, matcher: Matcher):
    # 指令冷却检查
    config = get_plugin_config(AiChatConfig)
    if not check_cooldown(f"pixiv_{event.user_id}", config.cooldown_seconds):
        await matcher.finish(f"太快啦，请{config.cooldown_seconds}秒后再试")
        return
    # 指令参数校验
    mode = event.get_plaintext().replace("/pixiv", "").strip()
    if mode not in ALLOWED_MODES:
        await matcher.finish("无效参数")
        return

    # 获取事件，模式以及排行榜本地信息
    # 减少一天的正确用法不是直接d-1
    time = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    mode = event.get_plaintext().replace("/pixiv", "").strip() or "day"
    # 主要处理逻辑
    while True:
        info_Path = Path(get_plugin_data_dir()) / "pixiv" / "ranking_info"/ f"{time}-{mode}.json"
        if query_check(time, mode):
            # 本地排行榜信息存在时就直接从本地获取，不获取了
            info_list = json.loads(info_Path.read_text(encoding="utf-8"))
            for _ in range(10):
                pic_info: dict = random.choice(info_list)
                # 这里要加一个图片数量判定，超过5的就不发了
                pic_list = resource_check(pic_info=pic_info, num=5)
                if pic_check(pic_list):
                    continue
                else:
                    break
            else:
                return await matcher.finish("今天的新图都发过了，明天再来吧")
            break
        else:
            # 查询排行榜信息并保存到本地
            acc_token = await get_access_token()
            rank_info = await get_rank_info(acc_token, mode)
            info_Path.write_text(json.dumps(rank_info, ensure_ascii=False, indent=2), encoding="utf-8")
            continue

    # 将pic_url
    for pic_url in pic_list:
        img_bytes = await get_pixiv_image(pic_url)
        # 图片下载失败提示
        if img_bytes is None:
            await matcher.send(MessageSegment.text("这张图下载失败了，请再抽一次"))
            continue
        else:
            await matcher.send(MessageSegment.image(img_bytes))
    return await matcher.finish()
                

async def get_rank_info(access_token: str, mode: str) -> list[dict]:
    """
    通过access_token来获取排行榜信息，包含mode选择不同类型的排行榜
    """
    config = get_plugin_config(AiChatConfig)
    client_kwargs = {}
    if config.proxy:
        client_kwargs["proxy"] = config.proxy
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "PixivAndroidApp/6.182.0",
        "App-OS": "android",
        "App-OS-Version": "15.0",
        "App-Version": "6.182.0",
        "Accept-Language": "zh-CN",
    }

    params = {
        "mode": mode,
        # "data": " ",
        # "offset": " ",
    } 
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0), **client_kwargs) as client:
        try:
            resp = await client.get(
                "https://app-api.pixiv.net/v1/illust/ranking",
                headers=headers,
                params=params
            )
            return resp.json().get("illusts")
        except Exception as e:
            print(f"获取排行榜信息失败，失败原因{e}")
            return []


async def get_img_info():
    """
    通过pid获取图片url
    """
    config = get_plugin_config(AiChatConfig)
    client_kwargs = {}
    if config.proxy:
        client_kwargs["proxy"] = config.proxy

async def get_access_token() -> str:
    """
    通过Pixiv的refresh_token获取access_token
    """
    config = get_plugin_config(AiChatConfig)
    client_kwargs = {}
    if config.proxy:
        client_kwargs["proxy"] = config.proxy
    data = {
        "grant_type": "refresh_token",
        "refresh_token": random.choice(config.refresh_token),
        "client_id": "MOBrBDS8blbauoSck0ZfDbtuzpyT",
        "client_secret": "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj",
        "include_policy": "true"
        }
    headers = {
        "User-Agent": "PixivAndroidApp/6.182.0"
        }
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0), **client_kwargs) as client:
        try:
            resp = await client.post(
                "https://oauth.secure.pixiv.net/auth/token",
                headers=headers,
                data=data
            )
            return resp.json().get("access_token")
        except Exception as e:
            print(f"获取访问token失败，失败原因{e}")
            return ""


async def get_pixiv_image(url: str) -> bytes | None:
    """
    获取图片的二进制内容径
    """
    config = get_plugin_config(AiChatConfig)
    client_kwargs = {}
    if config.proxy:
        client_kwargs["proxy"] = config.proxy
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0), **client_kwargs) as client:
        try:
            resp = await client.get(
                url,
                headers = {
                    "Referer": "https://www.pixiv.net/",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                }
            )
            return resp.content
        except Exception:
            return None
        
    


def query_check(time: str, mode: str) -> bool:
    """
    检查是否存在对应日期的文件
    """
    info_Path = Path(get_plugin_data_dir()) / "pixiv" / "ranking_info"/ f"{time}-{mode}.json"
    return info_Path.exists()


def pic_check(pic_id: list) -> bool:
    """
    检查图片是否发过了，文件不存在就新建并返回False
    """
    data_Path = Path(get_plugin_data_dir()) / "pixiv" / "sended.json"
    data_Path.parent.mkdir(parents=True, exist_ok=True)

    if data_Path.exists():
        sended_list = json.loads(data_Path.read_text())
    else:
        sended_list = []

    ids = [Path(i).stem for i in pic_id]

    if any(i in sended_list for i in ids):
        return True   # 发过了

    sended_list.extend(ids)
    data_Path.write_text(json.dumps(sended_list, ensure_ascii=False))
    return False      # 没发过，已标记


def resource_check(pic_info: dict, num: int = 5) -> list:
    """
    检查这个作品是否是多图资源，如果图片数量超过指定数量就返回空列表，因为有可能是漫画作品
    """
    _list = []
    print(pic_info)
    if pic_info["meta_single_page"]:
        pic_url = pic_info["meta_single_page"]["original_image_url"]
        _list.append(pic_url)
        return _list
    
    if pic_info["meta_pages"]:
        pic_url_list = pic_info["meta_pages"]
        if len(pic_url_list) > num:
            return []
        else:
            for img in pic_url_list:
                # 换成large图源，原图有的太大了发不出来
                _list.append(img["image_urls"]["large"])
            return _list
    
    return []
    