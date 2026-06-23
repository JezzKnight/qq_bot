import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)
nonebot.load_builtin_plugins("echo", "single_session")
nonebot.load_plugin("qq_bot.plugins.ai_chat")

if __name__ == "__main__":
    nonebot.run()