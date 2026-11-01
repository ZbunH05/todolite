"""Phân luồng khởi chạy. Giữ import tối thiểu để mỗi chế độ chỉ nạp đúng thứ nó cần."""
import sys

from .paths import VENDOR_DIR, log
from .win32 import WM_APP_OPEN, WM_CLOSE, FindWindowW, PostMessageW, AGENT_WINDOW_CLASS, acquire_mutex, post_agent

AGENT_MUTEX = "Local\\TodoLite.Agent"


def start_agent(autostarted, open_ui):
    mutex = acquire_mutex(AGENT_MUTEX)
    if mutex is None:
        return
    from .agent import Agent
    Agent(autostarted=autostarted, open_ui=open_ui).run()


def launch():
    """Mở bằng shortcut: hiện giao diện, tự dựng agent nếu nó chưa chạy."""
    if not post_agent(WM_APP_OPEN):
        start_agent(autostarted=False, open_ui=True)


def stop_agent():
    hwnd = FindWindowW(AGENT_WINDOW_CLASS, None)
    if hwnd:
        PostMessageW(hwnd, WM_CLOSE, 0, 0)


def run_ui():
    sys.path.insert(0, VENDOR_DIR)
    from .ui.app import run
    run()


def main(argv):
    command = argv[0] if argv else ""
    try:
        if command == "--background":
            start_agent(autostarted=True, open_ui=False)
        elif command == "--ui":
            run_ui()
        elif command == "--telegram":
            from .telegram import main as send_telegram
            send_telegram()
        elif command == "--quit":
            stop_agent()
        else:
            launch()
    except Exception:
        import traceback
        log(traceback.format_exc())
        raise
