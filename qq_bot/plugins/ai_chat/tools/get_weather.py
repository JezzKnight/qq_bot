from .registry import register_tool
import httpx

@register_tool(
    name="get_weather",
    description="获取当前的天气信息以及查询未来的天气信息",
    parameters={"type": "object",
                "properties": {},
                "required": []},
)
async def get_weather(place: str, day: int | None = None, sheng: str | None = None):
    url = "https://cn.apihz.cn/api/tianqi/tqyb.php"
    params = {
        "id": 10013869,
        "key": "3647cc4687f8c9a563bc72246b01f5e0",
        "sheng": sheng,
        "place": place,
        "day":day
    }
    _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
    response = await _client.get(
        url=url,
        params=params
    )

    return response.json()

if __name__ == "__main__":
    import asyncio
    async def test():
        response = await get_weather(place="深圳")
        print(response)

    asyncio.run(test())