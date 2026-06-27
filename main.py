"""
校园网登录工具 — 程序入口 (多学校支持)

用法:
  python -m dormnet_login.main          # 普通启动 (显示窗口)
  python -m dormnet_login.main --silent # 静默启动 (最小化到任务栏, 用于开机自启)
"""

import os
import sys

from .gui import CampusLoginGUI
from .logger import setup_logging, get_logger


def main():
    """程序主入口"""
    # 初始化日志系统
    log_dir = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "dormnet_login", "logs",
    )
    setup_logging(log_dir)
    log = get_logger(__name__)
    log.info("=" * 50)
    log.info("程序启动 v2.0.1")

    silent = "--silent" in sys.argv
    if silent:
        log.info("运行模式: silent")
    app = CampusLoginGUI(silent=silent)
    app.run()
    log.info("程序正常结束")


if __name__ == "__main__":
    main()
