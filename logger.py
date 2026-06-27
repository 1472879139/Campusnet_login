"""
应用日志系统

日志文件位置: %APPDATA%/dormnet_login/logs/app.log
按天轮转，保留最近 14 天，启动时自动清理过期文件。

用法:
    from .logger import setup_logging, get_logger

    setup_logging(log_dir)           # 在 main.py 启动时调用一次
    log = get_logger(__name__)       # 在各模块中获取 logger
    log.info("message")
    log.error("message", exc_info=True)
"""

import logging
import logging.handlers
import os
import re
import time
from typing import Optional

_LOG_DIR: Optional[str] = None


def _cleanup_old_logs(log_dir: str, max_days: int = 14) -> int:
    """清理超过 max_days 天的日志文件，返回删除文件数

    匹配 app.log 当前文件、app.log.YYYY-MM-DD 默认轮转文件、
    以及 namer 生成的 app-YYYY-MM-DD.log 文件。
    """
    if not os.path.isdir(log_dir):
        return 0

    cutoff_time = time.time() - max_days * 86400
    deleted = 0

    try:
        for filename in os.listdir(log_dir):
            filepath = os.path.join(log_dir, filename)
            if not os.path.isfile(filepath):
                continue
            # 匹配: app.log / app.log.2026-06-27 / app-2026-06-27.log
            if not (filename == "app.log" or
                    filename.startswith("app.log.") or
                    (filename.startswith("app-") and filename.endswith(".log"))):
                continue
            if os.path.getmtime(filepath) < cutoff_time:
                try:
                    os.remove(filepath)
                    deleted += 1
                except OSError:
                    pass
    except OSError:
        pass

    return deleted


def setup_logging(log_dir: str, level: int = logging.INFO) -> None:
    """初始化日志系统

    在程序启动时调用一次。创建日志目录、配置 TimedRotatingFileHandler、
    清理过期日志文件。

    Args:
        log_dir: 日志文件存放目录（如 %APPDATA%/dormnet_login/logs）
        level: 日志级别，默认 INFO
    """
    global _LOG_DIR
    _LOG_DIR = log_dir

    os.makedirs(log_dir, exist_ok=True)

    # 清理过期日志
    deleted = _cleanup_old_logs(log_dir, max_days=14)

    # 移除指向不存在目录的旧 handler（跨测试/重启场景）
    root_logger = logging.getLogger("dormnet")
    root_logger.setLevel(level)
    log_path = os.path.join(log_dir, "app.log")

    for h in list(root_logger.handlers):
        if isinstance(h, logging.handlers.TimedRotatingFileHandler):
            # 检查是否指向当前 log_dir；否则移除（如测试临时目录残留）
            if os.path.dirname(h.baseFilename) != os.path.abspath(log_dir):
                root_logger.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass

    # 避免重复添加 handler
    if not any(isinstance(h, logging.handlers.TimedRotatingFileHandler)
               for h in root_logger.handlers):
        handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_path,
            when="midnight",
            interval=1,
            backupCount=14,
            encoding="utf-8",
            delay=False,  # 立即创建文件（方便验证日志系统正常启动）
        )

        # 轮转后的文件命名: app.log.2026-06-27
        handler.suffix = "%Y-%m-%d"
        # 使用自定义 namer 确保扩展名正确
        handler.namer = lambda name: name.replace(".log.", "-") + ".log"

        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)-5s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

        if deleted > 0:
            root_logger.info("清理了 %d 个过期日志文件", deleted)


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger

    返回 dormnet 命名空间下的 logger，继承根 handler 配置。

    Args:
        name: 模块名，通常传 __name__ 会自动提取短名称
              如 dormnet_login.client → 记录为 "client"
    """
    # 简化 logger 名称: dormnet_login.xxx → xxx
    short_name = name.split(".")[-1] if "." in name else name
    return logging.getLogger(f"dormnet.{short_name}")


# 密码参数名列表（不区分大小写）
_PASSWORD_PARAMS = {"user_password", "password", "passwd", "pwd"}


def sanitize_url(url: str) -> str:
    """脱敏 URL 中的密码参数，将 user_password=xxx 替换为 user_password=***"""
    for param in _PASSWORD_PARAMS:
        # 匹配 param=任意非&字符
        pattern = re.compile(rf"({param}=)([^&\s#]+)", re.IGNORECASE)
        url = pattern.sub(r"\1***", url)
    return url
