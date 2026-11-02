"""Đường dẫn dùng chung và log siêu nhẹ.

Agent chạy nền nên module này cố tình không import logging/pathlib: mỗi module
stdlib kéo thêm vài trăm KB RAM mà chạy suốt ngày.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_SCRIPT = os.path.join(ROOT, "run.pyw")
VENDOR_DIR = os.path.join(ROOT, "vendor")
ICON_PATH = os.path.join(ROOT, "assets", "app.ico")
ICON_ALERT_PATH = os.path.join(ROOT, "assets", "app_alert.ico")
ICON_PNG_PATH = os.path.join(ROOT, "assets", "app.png")
FONT_PATHS = (os.path.join(ROOT, "assets", "fonts", "BeVietnamPro-Regular.ttf"), os.path.join(ROOT, "assets", "fonts", "BeVietnamPro-SemiBold.ttf"))

# TODOLITE_DATA cho phép chạy thử trên dữ liệu riêng, không đụng dữ liệu thật hay đăng ký hệ thống.
SANDBOX = bool(os.environ.get("TODOLITE_DATA"))
DATA_DIR = os.environ.get("TODOLITE_DATA") or os.path.join(os.environ["LOCALAPPDATA"], "TodoLite")
DB_PATH = os.path.join(DATA_DIR, "todo.db")
LOG_PATH = os.path.join(DATA_DIR, "app.log")
LOG_LIMIT = 256 * 1024


def pythonw():
    """Đường dẫn pythonw.exe thật. Launcher của venv sẽ đẻ thêm một tiến trình thừa."""
    base = getattr(sys, "_base_executable", None) or sys.executable
    candidate = os.path.join(os.path.dirname(base), "pythonw.exe")
    return candidate if os.path.isfile(candidate) else base


def log(message):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > LOG_LIMIT:
            os.replace(LOG_PATH, LOG_PATH + ".1")
        with open(LOG_PATH, "a", encoding="utf-8") as stream:
            stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass
