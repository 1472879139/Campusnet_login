"""
校园网登录/注销 HTTP 客户端 — 多学校支持

基于 DormNet-GUI 项目 CQUPT 适配实现的 Python 移植:
  dormnet-targets/src/commonMain/kotlin/.../targets/CQUPT.kt

支持 Dr.COM ePortal 协议的学校均可使用，认证配置通过 set_school() 动态切换。

登录流程:
  1. GET 网关地址，禁止重定向
  2. 从 302 Location 头解析 wlanuserip, wlanacname, wlanacip, mac
  3. 携带网络参数 + 用户凭据向认证服务器发起 GET 请求
  4. 解析 JSONP 响应，检查 result == "1"
"""

import base64
import json
import socket
import subprocess
import urllib.request
import urllib.error
import urllib.parse
import uuid
from typing import Optional

from .config import (
    PROBE_URLS,
    REQUEST_TIMEOUT,
    get_school,
    get_effective_auth_config,
    get_device_config,
    get_operator_map,
)


class LoginError(Exception):
    """登录/注销过程中的错误"""
    pass


class NetworkParamsError(LoginError):
    """获取网络参数失败 (可能未连接校园网)"""
    pass


class NetworkError(LoginError):
    """网络层错误（超时、连接失败等）—— 请求可能已被服务器处理但响应未到达"""
    pass


def _get_mac_for_ip(local_ip: str) -> str:
    """通过 PowerShell 获取指定 IP 对应网卡的 MAC 地址

    在 Hyper-V/VPN 等虚拟网卡存在时，uuid.getnode() 可能返回错误的 MAC，
    因此优先通过 IP 反查正确网卡。
    """
    try:
        ps_cmd = (
            f"Get-NetIPAddress -AddressFamily IPv4 -IPAddress '{local_ip}' "
            f"| Get-NetAdapter | Select -ExpandProperty MacAddress"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NoLogo", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            mac = result.stdout.strip().replace("-", ":").upper()
            if len(mac) == 17 and mac.count(":") == 5:
                return mac
    except Exception:
        pass
    return ""


def _build_local_network_params_static(gateway_host: str, gateway_port: int) -> dict:
    """从本机系统信息构造网络参数（兜底方案）

    当已处于认证状态时，校园网强制门户不会触发 302 重定向，
    无法通过 get_network_params() 获取参数。但注销请求实际只需要
    wlan_user_ip 和 wlan_user_mac（wlan_ac_ip/wlan_ac_name 固定为空），
    这两个值均可从本机获取，无需依赖网络劫持。

    gateway_host / gateway_port 用于 UDP 探测出口网卡 IP。
    """
    local_ip = "0.0.0.0"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect((gateway_host, gateway_port))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    mac = _get_mac_for_ip(local_ip)
    if not mac:
        mac_int = uuid.getnode()
        mac = ":".join(
            f"{(mac_int >> (8 * i)) & 0xFF:02X}" for i in range(5, -1, -1)
        )

    return {
        "wlanuserip": local_ip,
        "wlanacname": "",
        "wlanacip": "",
        "mac": mac,
    }


class CampusClient:
    """校园网认证客户端 — 支持多学校动态切换"""

    def __init__(self, timeout: int = REQUEST_TIMEOUT):
        self._timeout = timeout
        self._cached_params: Optional[dict] = None
        self._school_key: str = "cqupt"
        self._campus_key: Optional[str] = None

    # ------------------------------------------------------------------
    # 学校/校区切换
    # ------------------------------------------------------------------

    def set_school(self, school_key: str, campus_key: Optional[str] = None) -> None:
        """切换到指定学校和校区"""
        self._school_key = school_key
        self._campus_key = campus_key

    def get_school_name(self) -> str:
        """获取当前学校显示名称"""
        return get_school(self._school_key)["name"]

    def _get_auth_config(self) -> dict:
        """解析当前学校+校区的有效认证配置"""
        return get_effective_auth_config(self._school_key, self._campus_key)

    def _get_device_config(self) -> dict:
        """获取当前学校的设备类型配置"""
        return get_device_config(self._school_key)

    def _get_operator_map(self) -> dict:
        """获取当前学校的运营商选项"""
        return get_operator_map(self._school_key)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def get_cached_params(self) -> Optional[dict]:
        """获取登录时缓存的网络参数 (供跨会话持久化使用)"""
        return self._cached_params

    def set_cached_params(self, params: Optional[dict]) -> None:
        """恢复缓存的网络参数 (从配置文件恢复，供跨会话注销使用)"""
        self._cached_params = params

    def build_local_network_params(self) -> dict:
        """使用当前学校配置构造网络参数（兜底方案）"""
        auth_cfg = self._get_auth_config()
        return _build_local_network_params_static(
            auth_cfg["gateway_host"], auth_cfg["gateway_port"]
        )

    def check_auth_status(self) -> str:
        """
        检测当前网络认证状态 (不依赖缓存)

        利用校园网强制门户机制: 未认证时外部 HTTP 请求会被 302 重定向到认证页面;
        已认证时请求直接到达目标服务器返回 200。

        返回:
            "authenticated"     - 已认证 (HTTP 请求直接成功，无重定向)
            "not_authenticated" - 未认证 (触发 302 重定向，在校园网内但未登录)
            "offline"           - 不在校园网环境 (所有探测地址均网络错误)
        """
        saw_redirect = False

        for probe_url in PROBE_URLS:
            req = urllib.request.Request(probe_url, method="GET")
            opener = urllib.request.build_opener(_NoRedirectHandler)
            try:
                opener.open(req, timeout=self._timeout)
                return "authenticated"
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 303, 307, 308):
                    saw_redirect = True
            except urllib.error.URLError:
                continue

        return "not_authenticated" if saw_redirect else "offline"

    def get_network_params(self) -> dict:
        """
        第一步: 通过访问外部 HTTP 地址触发校园网强制门户重定向

        校园网会在未认证时拦截外部 HTTP 请求，302 重定向到认证页面。
        从重定向 URL 中提取 wlanuserip, wlanacname, wlanacip, mac 等参数。

        返回: {"wlanuserip": ..., "wlanacname": ..., "wlanacip": ..., "mac": ...}

        抛出 NetworkParamsError: 如果无法获取参数
        """
        school_name = self.get_school_name()
        last_error = None
        saw_redirect = False

        for probe_url in PROBE_URLS:
            try:
                return self._try_get_params(probe_url)
            except NetworkParamsError as e:
                last_error = e
                if "未触发" in str(e) or "返回 HTTP" in str(e):
                    saw_redirect = False
                else:
                    saw_redirect = True
                continue

        if not saw_redirect:
            raise NetworkParamsError(
                "无法获取校园网认证参数。\n\n"
                "所有探测地址均未触发校园网重定向，可能原因:\n"
                "  1. 已开启 VPN 或代理软件 — 请关闭后重试\n"
                f"  2. 未连接 {school_name} 校园网 (WiFi 或有线)\n"
                "  3. 已处于认证状态"
            )

        if last_error:
            raise last_error
        raise NetworkParamsError(
            f"无法获取网络参数: 所有探测地址均失败，"
            f"请确认已连接 {school_name} 校园网 (WiFi 或有线)"
        )

    def _try_get_params(self, probe_url: str) -> dict:
        """尝试访问探测 URL，拦截强制门户重定向"""
        req = urllib.request.Request(probe_url, method="GET")
        opener = urllib.request.build_opener(_NoRedirectHandler)

        try:
            opener.open(req, timeout=self._timeout)
            raise NetworkParamsError(
                f"探测 {probe_url} 未触发重定向"
            )
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                location = e.headers.get("Location", "")
                if location:
                    return self._parse_location(location)
            raise NetworkParamsError(
                f"探测 {probe_url} 返回 HTTP {e.code}"
            )
        except urllib.error.URLError as e:
            raise NetworkParamsError(
                f"无法连接探测地址 ({probe_url}): {e.reason}"
            )

    def login(
        self,
        username: str,
        password: str,
        device: str = "mobile",
        operator: str = "telecom",
    ) -> str:
        """
        第二步: 执行校园网认证登录

        参数:
            username: 校园网账号
            password: 校园网密码
            device:   设备类型 ("pc" 或 "mobile")
            operator: 运营商 ("telecom" / "cmcc" / "unicom")

        返回: 登录成功时的服务器消息

        抛出 LoginError: 登录失败时
        """
        device_config = self._get_device_config()
        operator_map = self._get_operator_map()

        if device not in device_config:
            raise LoginError(f"不支持的设备类型: {device}")
        if operator not in operator_map:
            raise LoginError(f"不支持的运营商: {operator}")

        if self._cached_params:
            net_params = self._cached_params
        else:
            net_params = self.get_network_params()
            self._cached_params = net_params

        dev = device_config[device]
        user_account = f",{dev['account_prefix']},{username}@{operator}"

        params = {
            "c": "Portal",
            "a": "login",
            "callback": dev["callback"],
            "login_method": "1",
            "user_account": user_account,
            "user_password": password,
            "wlan_user_ip": net_params["wlanuserip"],
            "wlan_user_ipv6": "",
            "wlan_user_mac": net_params["mac"],
            "wlan_ac_ip": "",
            "wlan_ac_name": "",
            "jsVersion": "3.3.3",
        }

        headers = self._build_headers(dev["user_agent"])

        return self._do_request(
            url=self._get_auth_config()["auth_url"],
            params=params,
            headers=headers,
            operation="登录",
        )

    def logout(
        self,
        username: str,
        password: str,
        device: str = "mobile",
        operator: str = "telecom",
    ) -> str:
        """
        注销校园网认证

        参数同 login()
        返回: 注销成功时的服务器消息
        """
        device_config = self._get_device_config()
        operator_map = self._get_operator_map()

        if device not in device_config:
            raise LoginError(f"不支持的设备类型: {device}")
        if operator not in operator_map:
            raise LoginError(f"不支持的运营商: {operator}")

        net_params = self._cached_params
        if not net_params:
            try:
                net_params = self.get_network_params()
            except NetworkParamsError:
                net_params = self.build_local_network_params()

        dev = device_config[device]
        user_account = f",{dev['account_prefix']},{username}@{operator}"

        params = {
            "c": "Portal",
            "a": "logout",
            "callback": dev["callback"],
            "login_method": "1",
            "user_account": user_account,
            "user_password": password,
            "wlan_user_ip": net_params["wlanuserip"],
            "wlan_user_ipv6": "",
            "wlan_user_mac": net_params["mac"],
            "wlan_ac_ip": "",
            "wlan_ac_name": "",
            "jsVersion": "3.3.3",
        }

        headers = self._build_headers(dev["user_agent"])

        try:
            return self._do_request(
                url=self._get_auth_config()["auth_url"],
                params=params,
                headers=headers,
                operation="注销",
            )
        except NetworkError:
            try:
                status = self.check_auth_status()
                if status != "authenticated":
                    return "注销成功（服务器无响应，已通过状态检测确认）"
            except Exception:
                pass
            raise

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _build_headers(self, user_agent: str) -> dict:
        """根据当前学校的 auth_url 动态构造请求头"""
        auth_cfg = self._get_auth_config()
        auth_url = auth_cfg["auth_url"]
        parsed = urllib.parse.urlparse(auth_url)
        referer = f"{parsed.scheme}://{parsed.hostname}/"
        return {
            "User-Agent": user_agent,
            "Referer": referer,
            "DNT": "1",
        }

    def _parse_location(self, location: str) -> dict:
        """从网关重定向 URL 中解析网络参数"""
        if "?" in location:
            query = location.split("?", 1)[1]
        else:
            query = location

        parsed = urllib.parse.parse_qs(query)

        params = {
            "wlanuserip": parsed.get("wlanuserip", [""])[0],
            "wlanacname": parsed.get("wlanacname", [""])[0],
            "wlanacip": parsed.get("wlanacip", [""])[0],
            "mac": parsed.get("mac", [""])[0],
        }

        missing = [k for k, v in params.items() if not v]
        if missing:
            raise NetworkParamsError(
                f"网关重定向参数不完整，缺少: {', '.join(missing)}"
            )

        return params

    def _do_request(
        self,
        url: str,
        params: dict,
        headers: dict,
        operation: str,
    ) -> str:
        """
        发送认证请求并解析 JSONP 响应
        响应格式: callback({"result":"1","msg":"..."})
        """
        query_string = urllib.parse.urlencode(params)
        full_url = f"{url}?{query_string}"

        req = urllib.request.Request(full_url, method="GET")
        for key, value in headers.items():
            req.add_header(key, value)

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as e:
            raise NetworkError(f"{operation}失败: 无法连接认证服务器 - {e.reason}")
        except Exception as e:
            raise NetworkError(f"{operation}失败: {e}")

        return self._parse_response(body, operation)

    def _parse_response(self, body: str, operation: str) -> str:
        """解析 JSONP 响应，返回服务器消息"""
        if not body or len(body) <= 2:
            raise LoginError(f"{operation}失败: 服务器返回空响应")

        try:
            json_str = body
            if "(" in body and ")" in body:
                json_str = body[body.index("(") + 1: body.rindex(")")]

            data = json.loads(json_str)
        except (json.JSONDecodeError, ValueError) as e:
            raise LoginError(
                f"{operation}失败: 无法解析服务器响应\n响应内容: {body[:200]}"
            )

        result = data.get("result", "")
        message = data.get("msg", "")

        if result != "1":
            raise LoginError(
                f"{operation}失败: {self._friendly_error(message) or '未知错误'}"
            )

        return message or f"{operation}成功"

    def _friendly_error(self, raw_msg: str) -> str:
        """
        将服务器原始错误信息 Decode 并映射为用户友好的中文提示

        服务器返回的错误信息为 Base64 编码，解码后按关键词匹配:
          - "userid"         → 账号不存在
          - "ldap/auth"      → 密码错误
          - "operator"       → 运营商选择错误
          - "account"        → 账号异常（含运营商/套餐不匹配）
          - "product"        → 套餐/产品状态异常
        """
        if not raw_msg:
            return ""

        decoded = raw_msg
        try:
            raw_bytes = base64.b64decode(raw_msg)
            decoded = raw_bytes.decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            try:
                decoded = raw_bytes.decode("latin-1")
            except Exception:
                pass
        except Exception:
            pass

        decoded_lower = decoded.lower()

        if "userid" in decoded_lower:
            return "账号不存在，请检查学号是否正确"
        if "ldap" in decoded_lower or "auth" in decoded_lower:
            return "密码错误，请检查密码是否正确"
        if "operator" in decoded_lower or "isp" in decoded_lower or "unbind" in decoded_lower:
            return "运营商选择错误，请检查运营商设置"
        if "account" in decoded_lower:
            return f"账号异常: {decoded}"
        if "product" in decoded_lower:
            return f"套餐状态异常: {decoded}"

        return decoded if decoded != raw_msg else raw_msg


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """禁止自动重定向的 HTTP handler

    redirect_request 返回 None 时，urllib 会抛出 HTTPError。
    我们在 get_network_params() 中捕获 HTTPError，
    从 e.headers 提取 Location 头来获取网络参数。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
