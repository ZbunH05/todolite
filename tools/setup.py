"""Cài đặt TodoLite cho người dùng hiện tại, không cần quyền admin. Chạy lại bao nhiêu lần cũng được.

    py -3 tools\\setup.py                 cài đặt đầy đủ và mở app
    py -3 tools\\setup.py --no-autostart  cài đặt nhưng không tự chạy cùng Windows
    py -3 tools\\setup.py --uninstall     gỡ khỏi Windows, giữ nguyên dữ liệu task
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MIN_PYTHON = (3, 10)
SHORTCUT = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "TodoLite.lnk")


def step(message):
    print(f"  - {message}", flush=True)


def check_python():
    if sys.version_info < MIN_PYTHON:
        raise SystemExit(f"Cần Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} trở lên, máy đang dùng {sys.version.split()[0]}.")
    try:
        import tkinter  # noqa: F401
    except ImportError:
        raise SystemExit("Bản Python này thiếu tkinter. Hãy cài lại từ python.org và chọn mục 'tcl/tk and IDLE'.")
    step(f"Python {sys.version.split()[0]}")


def install_dependencies():
    from todolite.paths import VENDOR_DIR
    requirements = os.path.join(ROOT, "requirements.txt")
    command = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--upgrade",
               "--target", VENDOR_DIR, "-r", requirements]
    subprocess.run(command, check=True)
    step("Đã cài thư viện giao diện vào thư mục vendor")


def _quoted(value):
    return "'" + value.replace("'", "''") + "'"


def create_shortcut():
    from todolite.paths import ICON_PATH, RUN_SCRIPT, pythonw
    script = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_quoted(SHORTCUT)});"
              f"$s.TargetPath = {_quoted(pythonw())};"
              f"$s.Arguments = {_quoted(chr(34) + RUN_SCRIPT + chr(34))};"
              f"$s.WorkingDirectory = {_quoted(ROOT)};"
              f"$s.IconLocation = {_quoted(ICON_PATH)};"
              "$s.Description = 'TodoLite: to-do cá nhân siêu nhẹ';$s.Save()")
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], check=True)
    step("Đã tạo shortcut trong Start Menu")


def stop_agent():
    from todolite.win32 import AGENT_WINDOW_CLASS, WM_CLOSE, FindWindowW, PostMessageW
    hwnd = FindWindowW(AGENT_WINDOW_CLASS, None)
    if hwnd:
        PostMessageW(hwnd, WM_CLOSE, 0, 0)
        step("Đã tắt TodoLite đang chạy")


def install(args):
    from todolite import integration
    from todolite.paths import RUN_SCRIPT, pythonw
    print("Cài đặt TodoLite")
    check_python()
    install_dependencies()
    integration.register_app()
    step("Đã đăng ký thông báo với Windows")
    create_shortcut()
    integration.set_autostart(not args.no_autostart)
    step("Đã tắt tự khởi động" if args.no_autostart else "Đã bật tự khởi động cùng Windows")
    if not args.no_launch:
        subprocess.Popen([pythonw(), RUN_SCRIPT], cwd=ROOT)
        step("Đã mở TodoLite, icon nằm ở khay hệ thống góc phải taskbar")
    print("Xong!")


def uninstall():
    from todolite import integration
    from todolite.paths import DATA_DIR
    print("Gỡ TodoLite")
    stop_agent()
    integration.set_autostart(False)
    integration.unregister_app()
    if os.path.exists(SHORTCUT):
        os.remove(SHORTCUT)
    step("Đã gỡ tự khởi động, shortcut và các đăng ký hệ thống")
    print(f"Dữ liệu task vẫn được giữ tại: {DATA_DIR}")
    print("Muốn xoá hẳn dữ liệu, hãy tự xoá thư mục đó.")


def main():
    parser = argparse.ArgumentParser(description="Cài đặt hoặc gỡ TodoLite")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--no-autostart", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    args = parser.parse_args()
    if args.uninstall:
        uninstall()
    else:
        install(args)


if __name__ == "__main__":
    main()
