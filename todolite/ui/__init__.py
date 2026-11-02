"""Giao diện. Dùng bản darkdetect rút gọn: bản gốc hỏi WMI phiên bản Windows ngay lúc nạp, tốn 70 ms mỗi lần mở cửa sổ.
packaging cũng được thay: CustomTkinter chỉ dùng nó để so Python < 3.10, mà nạp packaging.version tốn 11 ms."""
import sys
import types
import winreg

THEME_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def system_theme():
    """'Dark' hoặc 'Light' theo cài đặt của Windows, thay cho darkdetect.theme()."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, THEME_KEY) as key:
            return "Light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "Dark"
    except OSError:
        return "Light"


_detector = types.ModuleType("darkdetect")
_detector.theme = system_theme
sys.modules.setdefault("darkdetect", _detector)


def _version(text):
    """Thay packaging.version.parse cho chuỗi số chấm như '3.15.2' hay '9.0.4'; phần chữ (a1, rc2) bị bỏ."""
    return tuple(int(part) for part in text.split(".") if part.isdigit())


if "packaging" not in sys.modules:
    _version_module = types.ModuleType("packaging.version")
    _version_module.parse = _version
    _packaging = types.ModuleType("packaging")
    _packaging.version = _version_module
    sys.modules["packaging"] = _packaging
    sys.modules["packaging.version"] = _version_module
