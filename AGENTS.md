# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project overview

CQUPT 校园网登录工具 — a Windows desktop app that automates campus network authentication for 重庆邮电大学 (CQUPT). It's a Python GUI wrapper around the ePortal captive-portal login protocol, allowing users to authenticate with one click and spoof device type to bypass single-device limits.

The login logic is ported from the reference Kotlin implementation in the sibling `dormnet-gui` project (`dormnet-targets/src/commonMain/kotlin/.../targets/CQUPT.kt`).

## Commands

```bash
cd D:\dormnet_login

# Run from source
python run.py

# Run in silent mode (minimized to taskbar, for autostart)
python run.py --silent

# Build standalone exe
pyinstaller --onefile --windowed --name "CQUPT校园网登录" --clean run.py
# Output: dist/CQUPT校园网登录.exe
```

## Architecture

```
config.py              # Constants: probe URLs, auth server URL, device/operator configs
client.py              # CquptClient — two-step ePortal login/logout over HTTP
config_manager.py      # ConfigManager — JSON config file in %APPDATA%/dormnet_login/
autostart.py           # AutoStartManager — creates/removes .vbs launcher in Startup folder
gui.py                 # CquptLoginGUI — tkinter window, threading, keep-alive timer
main.py                # Python entry point (module: dormnet_login.main)
run.py                 # PyInstaller entry point (adds package dir to sys.path)
```

## Authentication flow (ePortal protocol)

1. **Detect captive portal** — Access an external HTTP URL (`PROBE_URLS` in config.py). The campus network firewall intercepts HTTP requests from unauthenticated clients and returns a 302 redirect to `http://192.168.200.2:801/eportal/` with query params carrying `wlanuserip`, `wlanacname`, `wlanacip`, and `mac`. A custom `_NoRedirectHandler` blocks urllib from following the redirect so the Location header can be captured.

2. **Send login request** — GET `http://192.168.200.2:801/eportal/` with query params including user credentials, device callback, and the network parameters from step 1. The response is JSONP (e.g. `dr1003({"result":"1","msg":"success"})`).

## Device spoofing

The ePortal server treats PC and Mobile devices differently, and most campuses allow one of each simultaneously. By changing `callback`, `account_prefix`, and `User-Agent`, the same physical machine can authenticate as a mobile device — enabling two PCs to share one account.

Device parameters are defined in `config.py` → `DEVICE_CONFIG`. The `callback` values (`dr1003` / `dr1005`) and `account_prefix` (`0` / `1`) are school-specific and were extracted from the CQUPT Kotlin adapter.

## Key design decisions

- **Network params are cached** (`CquptClient._cached_params`) because after successful login, the captive portal no longer intercepts external HTTP requests — so probe URLs return 200 instead of 302, making re-extraction impossible. The cache enables logout without re-detection.

- **Probe URLs are external HTTP sites** (not gateway IPs) because the captive portal only triggers on requests to the outside internet. Direct access to `192.168.200.2` does not produce a redirect.

- **HTTP not HTTPS for probes** — HTTPS requests fail during captive portal interception because the firewall can't present a valid TLS certificate for the redirected domain.

- **Threading model** — All HTTP calls run on daemon threads to avoid blocking the tkinter event loop. Results are dispatched back to the main thread via `root.after()`.

- **Config location** — `%APPDATA%/dormnet_login/config.json`. Password is encrypted using a key derived from the machine's MAC address (SHA-256 + XOR). `ConfigManager.load()` always merges with `DEFAULT_CONFIG` so new config keys are automatically populated on upgrade. Old plaintext `password` keys are auto-migrated to `encrypted_password` on next save.

- **Autostart mechanism** — A `.vbs` script in the Windows Startup folder (`%APPDATA%/Microsoft/Windows/Start Menu/Programs/Startup/`). The VBS approach (vs. registry `Run` key) is chosen so the entry is visible in Task Manager → Startup. When running as a frozen exe, the VBS launches the exe directly; when running from source, it launches `python.exe main.py --silent`.

- **Zero dependencies** — The app uses only Python standard library (tkinter, urllib, json, threading). This means no `pip install` step and simpler PyInstaller packaging.
