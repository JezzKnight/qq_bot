"""运行日志配置：将整个系统的日志写入项目根目录 logs/ 文件夹。

覆盖所有日志来源：
- NoneBot 框架自身日志（loguru logger）
- 项目内 ``logging.getLogger()`` 的标准库日志（经 LoguruHandler 桥接到 loguru）
- 项目内代码里的 ``print()`` 输出（经 stdout/stderr 拦截转发进 loguru，
  print 语句本身保留）

文件策略：
- ``logs/bot-YYYY-MM-DD.log``    全量 INFO+ 运行日志，按日期分文件，保留 30 天
- ``logs/error-YYYY-MM-DD.log``  ERROR+ 错误日志单独一份，同样按日期分文件
- 文件名中的 ``{time}`` 由 loguru 在每次轮转（每天 00:00）时替换为当天日期
- ``enqueue=True`` 后台线程异步落盘，避免阻塞事件循环
- ``encoding="utf-8"`` 保证 Windows 下中文不乱码
"""

import logging
import sys
from pathlib import Path
from typing import Any, TextIO

from nonebot.log import LoguruHandler, logger

# 项目根目录下的 logs 文件夹（本模块位于 qq_bot/logging_config.py）
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# 文件日志格式：带完整定位信息，便于事后排查
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "{name}:{function}:{line} | {message}"
)

# 幂等初始化标记（用可变 dict 避免 global 语句）
_state: dict[str, bool] = {"initialized": False}


class _StreamToLogger:
    """把 print()/sys.stdout 的输出转发进 loguru，实现「print 保留 + 全部进日志文件」。

    - 非空输出按指定级别写入 loguru（控制台与文件都会出现）
    - 空白输出直接透传给原流（保持换行等行为）
    - 其余属性（buffer/isatty/fileno/encoding 等）通过 __getattr__ 透传原流，
      避免破坏依赖 sys.stdout 具体行为的第三方库
    """

    def __init__(self, original: TextIO, level: str) -> None:
        self._original = original
        self._level = level

    def write(self, message: str) -> None:
        if message and message.strip():
            getattr(logger, self._level)(message.rstrip())
        else:
            self._original.write(message)

    def flush(self) -> None:
        self._original.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_original"), name)


def _install_stdout_capture() -> None:
    """用 loguru 包裹 stdout/stderr，使所有 print 输出也能写入日志文件。"""
    sys.stdout = _StreamToLogger(sys.stdout, "info")  # type: ignore[assignment]
    sys.stderr = _StreamToLogger(sys.stderr, "warning")  # type: ignore[assignment]


def init_logging() -> None:
    """初始化运行日志（幂等，重复调用安全）。"""
    if _state["initialized"]:
        return
    _state["initialized"] = True

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)

        # 标准 logging → loguru 桥接：项目里 logging.getLogger() 的日志统一进文件
        root = logging.getLogger()
        root.addHandler(LoguruHandler())
        root.setLevel(logging.INFO)

        # 这些 logger 已被挂上专属 LoguruHandler（uvicorn 系来自 nonebot 传入
        # uvicorn.run 的 LOGGING_CONFIG，apscheduler 来自 nonebot_plugin_apscheduler），
        # 但均未关闭传播，记录会继续上浮到 root 被再次桥接 → 控制台/文件双打。
        # 关闭传播使每条记录只经一条链路进入 loguru。
        # 注：uvicorn 启动时的 dictConfig 不含 propagate 键，不会覆盖此处预设值。
        for name in ("uvicorn.error", "uvicorn.access", "apscheduler"):
            logging.getLogger(name).propagate = False

        # 全量运行日志：按日期分文件（{time} 在轮转时替换为当天日期）
        logger.add(
            _LOG_DIR / "bot-{time:YYYY-MM-DD}.log",
            level="INFO",
            rotation="00:00",
            retention="30 days",
            encoding="utf-8",
            enqueue=True,
            diagnose=False,
            backtrace=False,
            format=_FILE_FORMAT,
        )
        # 错误日志单独一份，同样按日期分文件
        logger.add(
            _LOG_DIR / "error-{time:YYYY-MM-DD}.log",
            level="ERROR",
            rotation="00:00",
            retention="30 days",
            encoding="utf-8",
            enqueue=True,
            diagnose=False,
            backtrace=False,
            format=_FILE_FORMAT,
        )

        # 拦截 stdout/stderr，让项目里的 print 输出也写进日志文件
        _install_stdout_capture()

        logger.info("运行日志已初始化 -> {}", _LOG_DIR)
    except OSError as e:
        # 日志目录不可写时不能拖垮 bot，退化到仅控制台
        logger.warning("日志文件初始化失败，仅保留控制台输出: {}", e)
