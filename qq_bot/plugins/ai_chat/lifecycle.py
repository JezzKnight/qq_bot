from nonebot import get_driver
# 需要直接导入模块本身通过模块属性，直接导入对象在初始化的时候会将None值保存在本地命名空间
from . import client_factory
from . import memory_writing

_driver = get_driver()

@_driver.on_shutdown
async def cleanup():
    """退出时清理资源，结束生命周期"""
    if memory_writing._Memory is not None:
        await memory_writing._Memory.close()
    if client_factory._openai_client is not None:
        await client_factory._openai_client.close()
    if client_factory._gemini_client is not None:
        await client_factory._gemini_client.close()