"""Tích hợp với Windows qua registry của người dùng (HKCU, không cần quyền admin)."""
import winreg

from . import APP_ID, APP_NAME
from .paths import ICON_PNG_PATH, RUN_SCRIPT, pythonw

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
APP_ID_KEY = rf"Software\Classes\AppUserModelId\{APP_ID}"


def startup_command():
    return f'"{pythonw()}" "{RUN_SCRIPT}" --background'


def _set(key_path, name, value):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _read(key_path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except FileNotFoundError:
        return None


def _delete_value(key_path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        pass


def register_app():
    """Tên và icon cho toast. Chạy mỗi lần khởi động để tự cập nhật khi thư mục app bị di chuyển."""
    _set(APP_ID_KEY, "DisplayName", APP_NAME)
    _set(APP_ID_KEY, "IconUri", ICON_PNG_PATH)


def unregister_app():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, APP_ID_KEY)
    except FileNotFoundError:
        pass


def autostart_enabled():
    if _read(RUN_KEY, APP_NAME) is None:
        return False
    # Task Manager/Settings tắt app bằng cách đặt bit thấp của byte đầu trong StartupApproved.
    flags = _read(APPROVED_KEY, APP_NAME)
    return not (flags and flags[0] & 1)


def set_autostart(enabled):
    if enabled:
        _set(RUN_KEY, APP_NAME, startup_command())
    else:
        _delete_value(RUN_KEY, APP_NAME)
    _delete_value(APPROVED_KEY, APP_NAME)


def refresh_autostart():
    """Đã bật tự khởi động thì giữ lệnh khớp vị trí hiện tại của app và Python."""
    current = _read(RUN_KEY, APP_NAME)
    if current is not None and current != startup_command():
        _set(RUN_KEY, APP_NAME, startup_command())
