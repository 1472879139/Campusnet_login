"""
Windows 开机自启管理

通过 Windows 启动文件夹添加快捷方式实现开机自启。
使用 .vbs 脚本静默启动，避免弹出命令行窗口。

兼容 Windows 10 / 11。
"""

import os
import sys

from .logger import get_logger

log = get_logger(__name__)


class AutoStartManager:
    """
    Windows 开机自启管理

    原理: 在 Windows 启动文件夹创建 .vbs 脚本，
         系统登录时自动运行该脚本启动本程序。
    """

    # 快捷方式名称
    _LINK_NAME = "校园网登录.vbs"

    @classmethod
    def _get_startup_dir(cls) -> str:
        """获取 Windows 启动文件夹路径"""
        return os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu",
            "Programs", "Startup",
        )

    @classmethod
    def _get_link_path(cls) -> str:
        """获取启动快捷方式的完整路径"""
        return os.path.join(cls._get_startup_dir(), cls._LINK_NAME)

    @classmethod
    def _is_frozen(cls) -> bool:
        """检测是否为 PyInstaller 打包后的 exe 运行"""
        return getattr(sys, 'frozen', False)

    @classmethod
    def _get_exe_path(cls) -> str:
        """获取可执行文件路径"""
        if cls._is_frozen():
            # PyInstaller 打包后，sys.executable 就是 exe 本身
            return sys.executable
        else:
            # Python 脚本模式：python.exe + run.py
            return sys.executable

    @classmethod
    def _get_script_path(cls) -> str:
        """获取源码模式启动入口路径"""
        this_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(this_dir, "run.py")

    @classmethod
    def _build_launch_command(cls) -> str:
        """构建启动命令 (VBS 脚本内容)

        VBS 字符串内嵌引号需要用连续两个双引号转义。
        例如要在 VBS 字符串中表达双引号包围路径:
          命令: "C:\\path\\to\\exe" --silent
        VBS 应写为三个双引号开头、路径两侧各两个双引号、一个双引号结尾。
        """
        if cls._is_frozen():
            # exe 模式：直接运行 exe
            exe_path = sys.executable
            return (
                f'CreateObject("WScript.Shell").Run '
                f'"""{exe_path}"" --silent", '
                f'0, False'
            )
        else:
            # Python 脚本模式：用 python.exe 运行 run.py
            python_path = sys.executable
            script_path = cls._get_script_path()
            return (
                f'CreateObject("WScript.Shell").Run '
                f'"""{python_path}"" ""{script_path}"" --silent", '
                f'0, False'
            )

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    @classmethod
    def enable(cls) -> bool:
        """
        启用开机自启

        在启动文件夹创建 .vbs 脚本，静默启动本程序。

        返回: True 表示设置成功
        """
        startup_dir = cls._get_startup_dir()
        link_path = cls._get_link_path()

        # 确保启动文件夹存在
        os.makedirs(startup_dir, exist_ok=True)

        vbs_content = cls._build_launch_command()

        try:
            with open(link_path, "w") as f:
                f.write(vbs_content)
            log.info("开机自启已启用: %s", link_path)
            return True
        except (IOError, PermissionError) as e:
            log.error("开机自启启用失败: %s", e)
            return False

    @classmethod
    def disable(cls) -> bool:
        """
        禁用开机自启

        从启动文件夹删除 .vbs 脚本。

        返回: True 表示删除成功 (文件不存在也视为成功)
        """
        link_path = cls._get_link_path()

        if not os.path.exists(link_path):
            log.debug("开机自启已禁用（文件不存在）")
            return True

        try:
            os.remove(link_path)
            log.info("开机自启已禁用")
            return True
        except (IOError, PermissionError) as e:
            log.error("开机自启禁用失败: %s", e)
            return False

    @classmethod
    def is_enabled(cls) -> bool:
        """
        检查开机自启是否已启用

        检查启动文件夹中是否存在 .vbs 脚本。
        """
        return os.path.exists(cls._get_link_path())

    @classmethod
    def set_enabled(cls, enabled: bool) -> bool:
        """
        设置开机自启状态

        参数:
            enabled: True 启用, False 禁用
        返回: 操作是否成功
        """
        if enabled:
            return cls.enable()
        else:
            return cls.disable()
