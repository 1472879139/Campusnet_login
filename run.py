"""
校园网登录工具 — 打包入口

PyInstaller 打包用入口脚本，放在 dormnet_login 包同级目录。
"""

import sys
import os

# 确保包的父目录在 sys.path 中，才能从源码目录直接 import dormnet_login
_package_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_package_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from dormnet_login.main import main

if __name__ == "__main__":
    main()
