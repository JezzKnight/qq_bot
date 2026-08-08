"""查询 token 用量 —— 用户命令 /usage [YYYY-MM-DD]，不带日期默认查询今日"""
from datetime import date, datetime
from typing import NoReturn

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.rule import to_me

from qq_bot.plugins.ai_chat import token_usage

usage_cmd = on_command(
    "usage",
    rule=to_me(),
    aliases={"用量", "今日用量", "今日token"},
    block=True,
    force_whitespace=True,
)


def _parse_day(text: str) -> str | None:
    """校验并规范化 YYYY-MM-DD 格式，无效返回 None"""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


@usage_cmd.handle()
async def handle_usage(matcher: Matcher, args: Message = CommandArg()) -> NoReturn:
    """查询 token 用量：带日期查指定日期，不带日期查今天"""
    today_str = datetime.now().astimezone().strftime("%Y-%m-%d")

    arg = args.extract_plain_text().strip()
    if arg:
        day = _parse_day(arg)
        if day is None:
            await matcher.finish("📅 格式应为 YYYY-MM-DD，例：/usage 2026-08-07")
    else:
        day = today_str

    try:
        summary = await token_usage.get_date_summary(day)
    except Exception:  # noqa: BLE001
        await matcher.finish("❌ 用量统计服务暂不可用，请稍后重试。")

    prompt = summary["prompt_tokens"]
    cached = summary["cached_tokens"]
    completion = summary["completion_tokens"]
    miss = prompt - cached
    total = prompt + completion

    lines = [
        f"📊 {summary['day']} Token 用量",
        "────────────────────",
    ]
    if cached:
        lines.append(f"输入(缓存命中): {cached:,} Token")
    if miss:
        lines.append(f"输入(未命中): {miss:,} Token")
    if completion:
        lines.append(f"输出: {completion:,} Token")
    if total:
        lines.append(f"合计: {total:,} Token")
    if total == 0:
        label = "今日" if day == today_str else "该日"
        lines.append(f"{label}暂无 API 调用记录")

    await matcher.finish("\n".join(lines))
