"""
校园网登录常量定义 — 多学校支持

学校注册表集中管理各校的认证服务器地址、设备参数、运营商选项。
新增学校只需在 SCHOOL_REGISTRY 中添加条目即可。

设备参数参考:
  dormnet-targets/src/commonMain/kotlin/.../targets/CQUPT.kt
"""

from typing import Optional

# ------------------------------------------------------------------
# 通用常量 (所有学校共用)
# ------------------------------------------------------------------

# 探测地址 - 访问这些外部 HTTP URL 触发校园网强制门户重定向
# 校园网会拦截外部 HTTP 请求，302 重定向到认证页面
# 我们从重定向 URL 中提取 wlanuserip, mac 等网络参数
PROBE_URLS = [
    "http://www.baidu.com/",
    "http://httpbin.org/",
    "http://detectportal.firefox.com/success.txt",
    "http://www.msftconnecttest.com/redirect",
]

# HTTP 请求超时 (秒)
REQUEST_TIMEOUT = 10

# ------------------------------------------------------------------
# 共享设备/运营商配置 (Dr.COM ePortal 通用)
# ------------------------------------------------------------------

_DEFAULT_DEVICE_CONFIG = {
    "pc": {
        "callback": "dr1003",
        "account_prefix": "0",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0"
        ),
        "label": "PC (电脑端)",
    },
    "mobile": {
        "callback": "dr1005",
        "account_prefix": "1",
        "user_agent": (
            "Mozilla/5.0 (Linux; Android 10; K) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/141.0.0.0 Mobile Safari/537.36 EdgA/141.0.0.0"
        ),
        "label": "Mobile (手机端)",
    },
}

_DEFAULT_OPERATOR_MAP = {
    "telecom": "中国电信",
    "cmcc": "中国移动",
    "unicom": "中国联通",
}

# ------------------------------------------------------------------
# 学校注册表
# ------------------------------------------------------------------

SCHOOL_REGISTRY = {
    "cqupt": {
        "name": "重庆邮电大学",
        "auth_url": "http://192.168.200.2:801/eportal/",
        "gateway_host": "192.168.200.2",
        "gateway_port": 801,
        "device_config": _DEFAULT_DEVICE_CONFIG,
        "operator_map": _DEFAULT_OPERATOR_MAP,
    },
    "cwnu": {
        "name": "西华师范大学",
        "campuses": [
            {
                "key": "xinzheng",
                "label": "新政校区",
                "auth_url": "http://172.31.0.46:801/eportal/",
                "gateway_host": "172.31.0.46",
                "gateway_port": 801,
            },
            {
                "key": "huafeng",
                "label": "华凤校区",
                "auth_url": "http://172.26.3.60:801/eportal/",
                "gateway_host": "172.26.3.60",
                "gateway_port": 801,
            },
        ],
        "device_config": _DEFAULT_DEVICE_CONFIG,
        "operator_map": _DEFAULT_OPERATOR_MAP,
    },
}

# ------------------------------------------------------------------
# 便捷访问函数
# ------------------------------------------------------------------

def get_school(key: str) -> dict:
    """根据 key 获取学校配置"""
    return SCHOOL_REGISTRY[key]


def get_school_list() -> list[dict]:
    """获取学校列表，供下拉框使用"""
    return [
        {"key": key, "name": info["name"]}
        for key, info in SCHOOL_REGISTRY.items()
    ]


def get_campus_list(school_key: str) -> Optional[list[dict]]:
    """获取校区列表。单校区学校返回 None"""
    school = SCHOOL_REGISTRY[school_key]
    return school.get("campuses")


def get_effective_auth_config(school_key: str, campus_key: Optional[str]) -> dict:
    """解析学校+校区的有效认证配置"""
    school = SCHOOL_REGISTRY[school_key]
    campuses = school.get("campuses")
    if campuses and campus_key:
        for c in campuses:
            if c["key"] == campus_key:
                return c
        # campus_key 无效, 回退到第一个校区
        return campuses[0]
    # 单校区学校直接返回学校本身的配置
    return {
        "auth_url": school["auth_url"],
        "gateway_host": school["gateway_host"],
        "gateway_port": school["gateway_port"],
    }


def get_device_config(school_key: str) -> dict:
    """获取学校对应的设备类型配置"""
    return SCHOOL_REGISTRY[school_key]["device_config"]


def get_operator_map(school_key: str) -> dict:
    """获取学校对应的运营商选项"""
    return SCHOOL_REGISTRY[school_key]["operator_map"]


# ------------------------------------------------------------------
# 默认用户配置
# ------------------------------------------------------------------

DEFAULT_CONFIG = {
    "school": "cqupt",
    "campus": None,
    "device": "mobile",
    "operator": "telecom",
    "auto_start": False,
    "keep_alive": True,
    "keep_alive_interval": 300,
    "remember_password": True,
    "auto_login": False,
}
