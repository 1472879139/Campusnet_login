import os
import subprocess
import sys
import unittest
from unittest import mock


PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PARENT_DIR = os.path.dirname(PACKAGE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)


class SimpleVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeWidget:
    def __init__(self):
        self.config = {}

    def configure(self, **kwargs):
        self.config.update(kwargs)


class RecordingConfigManager:
    def __init__(self, initial=None):
        self.data = dict(initial or {})
        self.saved = None

    def load(self):
        return dict(self.data)

    def save(self, config):
        self.saved = dict(config)
        self.data = dict(config)


class FakeAutoStart:
    def __init__(self, success=True):
        self.success = success
        self.calls = []

    def set_enabled(self, enabled):
        self.calls.append(enabled)
        return self.success


class GuiRegressionTests(unittest.TestCase):
    def make_gui_shell(self, *, password="secret", interval="300"):
        from dormnet_login.gui import CquptLoginGUI

        gui = object.__new__(CquptLoginGUI)
        gui._username_var = SimpleVar("20240001")
        gui._password_var = SimpleVar(password)
        gui._device_var = SimpleVar("Mobile (手机端)")
        gui._operator_var = SimpleVar("中国电信")
        gui._auto_start_var = SimpleVar(False)
        gui._keep_alive_var = SimpleVar(False)
        gui._interval_var = SimpleVar(interval)
        gui._remember_password_var = SimpleVar(True)
        gui._auto_login_var = SimpleVar(False)
        gui._config = {}
        return gui

    def test_save_settings_never_persists_plaintext_password(self):
        gui = self.make_gui_shell(password="plain-secret")
        config_mgr = RecordingConfigManager({"encrypted_password": "ciphertext"})
        gui._config_mgr = config_mgr
        gui._show_popup = lambda *args: None
        gui._start_keep_alive = lambda: None
        gui._stop_keep_alive = lambda: None

        gui._on_save_settings()

        self.assertIsNotNone(config_mgr.saved)
        self.assertNotIn("password", config_mgr.saved)
        self.assertEqual(config_mgr.saved["encrypted_password"], "ciphertext")

    def test_keep_alive_interval_uses_safe_default_for_invalid_values(self):
        gui = self.make_gui_shell(interval="0")

        config = gui._collect_config()

        self.assertEqual(config["keep_alive_interval"], 300)

    def test_keep_alive_interval_has_minimum_for_small_positive_values(self):
        gui = self.make_gui_shell(interval="10")

        config = gui._collect_config()

        self.assertEqual(config["keep_alive_interval"], 30)

    def test_auto_start_toggle_persists_config_when_system_change_succeeds(self):
        gui = self.make_gui_shell()
        gui._auto_start_var = SimpleVar(True)
        gui._config_mgr = RecordingConfigManager({"auto_start": False})
        gui._autostart = FakeAutoStart(success=True)
        gui._set_message = lambda *args: None

        gui._on_auto_start_toggle()

        self.assertEqual(gui._autostart.calls, [True])
        self.assertTrue(gui._config_mgr.saved["auto_start"])

    def test_logout_allows_empty_credentials(self):
        gui = self.make_gui_shell(password="")
        gui._is_logging = False
        gui._actually_disconnected = False
        gui._draw_status_dot = mock.Mock()
        gui._set_message = mock.Mock()
        gui._set_logging_state = mock.Mock()
        started = []

        class FakeThread:
            def __init__(self, target, args, daemon):
                self.target = target
                self.args = args
                self.daemon = daemon

            def start(self):
                started.append(self.args)

        with mock.patch("dormnet_login.gui.threading.Thread", FakeThread):
            gui._on_logout()

        gui._set_logging_state.assert_called_once_with(True)
        self.assertEqual(started[0][0], "20240001")
        self.assertEqual(started[0][1], "")

    def test_logged_in_controls_stay_locked_without_credentials(self):
        gui = self.make_gui_shell(password="")
        gui._login_button = FakeWidget()
        gui._logout_button = FakeWidget()
        gui._username_entry = FakeWidget()
        gui._password_entry = FakeWidget()
        gui._device_combo = FakeWidget()
        gui._operator_combo = FakeWidget()
        gui._remember_password_cb = FakeWidget()

        gui._set_logged_in_controls()

        self.assertEqual(gui._username_entry.config["state"], "disabled")
        self.assertEqual(gui._password_entry.config["state"], "disabled")
        self.assertEqual(gui._device_combo.config["state"], "disabled")


class EntryPointRegressionTests(unittest.TestCase):
    def test_run_py_can_be_imported_from_package_directory(self):
        result = subprocess.run(
            [sys.executable, "-c", "import run"],
            cwd=PACKAGE_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_source_autostart_launches_run_py_not_main_py_directly(self):
        from dormnet_login.autostart import AutoStartManager

        with mock.patch.object(AutoStartManager, "_is_frozen", return_value=False):
            command = AutoStartManager._build_launch_command()

        self.assertIn("run.py", command)
        self.assertNotIn("main.py", command)


if __name__ == "__main__":
    unittest.main()
