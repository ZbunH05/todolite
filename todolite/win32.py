"""Khai báo Win32 API bằng ctypes: thay cho pywin32, gọn và không tốn thêm RAM."""
import ctypes
from ctypes import POINTER, WINFUNCTYPE, Structure, byref, c_int, c_ssize_t, c_ubyte, c_uint, c_ulong, c_ushort, c_void_p, c_wchar, c_wchar_p, sizeof
from ctypes import wintypes as w

LRESULT = c_ssize_t
WNDPROC = WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

# Thông điệp cửa sổ
WM_ACTIVATE, WM_DESTROY, WM_PAINT, WM_CLOSE, WM_ENDSESSION = 0x06, 0x02, 0x0F, 0x10, 0x16
WM_MOUSEACTIVATE, WM_MOUSEMOVE, WM_LBUTTONUP, WM_MOUSELEAVE = 0x21, 0x200, 0x202, 0x2A3
WM_ERASEBKGND, WM_TIMECHANGE, WM_SETFONT, WM_NCHITTEST = 0x14, 0x1E, 0x30, 0x84
WM_NCLBUTTONDBLCLK, WM_NCRBUTTONUP, WM_KEYDOWN, WM_CHAR, WM_COMMAND = 0xA3, 0xA5, 0x100, 0x102, 0x111
WM_TIMER, WM_CTLCOLOREDIT, WM_CONTEXTMENU, WM_EXITSIZEMOVE = 0x113, 0x133, 0x7B, 0x232
WM_POWERBROADCAST, WM_HOTKEY, WM_WTSSESSION_CHANGE, WM_NULL, WM_USER, WM_APP = 0x218, 0x312, 0x2B1, 0x00, 0x400, 0x8000
WM_APP_DATA = WM_APP + 1  # dữ liệu vừa đổi: agent tính lại lịch nhắc
WM_APP_OPEN = WM_APP + 2  # yêu cầu mở giao diện
WM_APP_SUMMARY = WM_APP + 3  # gửi lại tóm tắt hôm nay
WM_APP_TRAY = WM_APP + 4  # sự kiện từ icon khay hệ thống

# Kiểu cửa sổ
WS_POPUP, WS_CHILD, WS_VISIBLE = 0x80000000, 0x40000000, 0x10000000
WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x08, 0x80, 0x08000000
CS_DBLCLKS, CS_DROPSHADOW = 0x08, 0x20000
ES_AUTOHSCROLL, EN_CHANGE, EM_SETSEL = 0x80, 0x300, 0xB1
SW_HIDE, SW_SHOWNORMAL, SW_SHOWNOACTIVATE, SW_RESTORE = 0, 1, 4, 9
MA_NOACTIVATE, TME_LEAVE = 3, 0x02
SWP_NOZORDER, SWP_NOACTIVATE = 0x04, 0x10
HTCAPTION, IDC_ARROW = 2, 32512
VK_BACK, VK_RETURN, VK_ESCAPE, VK_CONTROL, VK_A, VK_T = 0x08, 0x0D, 0x1B, 0x11, 0x41, 0x54
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x01, 0x02, 0x4000

# Khay hệ thống
NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETVERSION = 0, 1, 2, 4
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO, NIF_SHOWTIP = 0x01, 0x02, 0x04, 0x10, 0x80
NIIF_USER, NOTIFYICON_VERSION_4 = 0x04, 4
NIN_SELECT, NIN_KEYSELECT, NIN_BALLOONUSERCLICK = WM_USER, WM_USER + 1, WM_USER + 5

# Menu, icon
MF_STRING, MF_CHECKED, MF_GRAYED, MF_SEPARATOR = 0x00, 0x08, 0x01, 0x800
TPM_RIGHTBUTTON, TPM_BOTTOMALIGN, TPM_RETURNCMD = 0x02, 0x20, 0x100
IMAGE_ICON, LR_LOADFROMFILE = 1, 0x10
SM_CXSMICON, SM_CYSMICON = 49, 50

# Hệ thống
PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC = 0x07, 0x12
WTS_SESSION_UNLOCK, WTS_SESSION_LOCK = 0x08, 0x07
ERROR_ALREADY_EXISTS = 183
MONITOR_DEFAULTTONULL, MONITOR_DEFAULTTONEAREST = 0, 2
ASFW_ANY = 0xFFFFFFFF
MB_ICONASTERISK = 0x40
QUNS_ACCEPTS_NOTIFICATIONS, QUNS_QUIET_TIME = 5, 6
DPI_PER_MONITOR_V2 = -4
DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, 2

# GDI
TRANSPARENT, SRCCOPY, NULL_PEN, DI_NORMAL = 1, 0x00CC0020, 8, 0x03
DT_LEFT, DT_CENTER, DT_RIGHT, DT_VCENTER, DT_SINGLELINE, DT_CALCRECT, DT_NOPREFIX, DT_END_ELLIPSIS = (
    0x00, 0x01, 0x02, 0x04, 0x20, 0x400, 0x800, 0x8000)
FW_NORMAL, FW_SEMIBOLD, DEFAULT_CHARSET, CLEARTYPE_QUALITY = 400, 600, 1, 5

AGENT_WINDOW_CLASS = "TodoLiteAgentWindow"
UI_WINDOW_CLASS = "TkTopLevel"


class GUID(Structure):
    _fields_ = [("Data1", c_ulong), ("Data2", c_ushort), ("Data3", c_ushort), ("Data4", c_ubyte * 8)]


class WNDCLASSEXW(Structure):
    _fields_ = [("cbSize", w.UINT), ("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", c_int),
                ("cbWndExtra", c_int), ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HANDLE),
                ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR),
                ("hIconSm", w.HICON)]


class NOTIFYICONDATAW(Structure):
    _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT),
                ("uCallbackMessage", w.UINT), ("hIcon", w.HICON), ("szTip", c_wchar * 128), ("dwState", w.DWORD),
                ("dwStateMask", w.DWORD), ("szInfo", c_wchar * 256), ("uVersion", w.UINT),
                ("szInfoTitle", c_wchar * 64), ("dwInfoFlags", w.DWORD), ("guidItem", GUID), ("hBalloonIcon", w.HICON)]


class PAINTSTRUCT(Structure):
    _fields_ = [("hdc", w.HDC), ("fErase", w.BOOL), ("rcPaint", w.RECT), ("fRestore", w.BOOL),
                ("fIncUpdate", w.BOOL), ("rgbReserved", c_ubyte * 32)]


class TRACKMOUSEEVENT(Structure):
    _fields_ = [("cbSize", w.DWORD), ("dwFlags", w.DWORD), ("hwndTrack", w.HWND), ("dwHoverTime", w.DWORD)]


class MONITORINFO(Structure):
    _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD)]


def _bind(dll, name, restype, *argtypes):
    function = getattr(dll, name)
    function.restype, function.argtypes = restype, argtypes
    return function


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32")
_shell32 = ctypes.WinDLL("shell32")

CreateMutexW = _bind(_kernel32, "CreateMutexW", w.HANDLE, c_void_p, w.BOOL, w.LPCWSTR)
GetModuleHandleW = _bind(_kernel32, "GetModuleHandleW", w.HMODULE, w.LPCWSTR)
GetCurrentProcess = _bind(_kernel32, "GetCurrentProcess", w.HANDLE)
K32EmptyWorkingSet = _bind(_kernel32, "K32EmptyWorkingSet", w.BOOL, w.HANDLE)

RegisterClassExW = _bind(_user32, "RegisterClassExW", w.ATOM, POINTER(WNDCLASSEXW))
CreateWindowExW = _bind(_user32, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, c_int, c_int,
                        c_int, c_int, w.HWND, w.HMENU, w.HINSTANCE, c_void_p)
DestroyWindow = _bind(_user32, "DestroyWindow", w.BOOL, w.HWND)
DefWindowProcW = _bind(_user32, "DefWindowProcW", LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
GetMessageW = _bind(_user32, "GetMessageW", c_int, POINTER(w.MSG), w.HWND, w.UINT, w.UINT)
TranslateMessage = _bind(_user32, "TranslateMessage", w.BOOL, POINTER(w.MSG))
DispatchMessageW = _bind(_user32, "DispatchMessageW", LRESULT, POINTER(w.MSG))
PostMessageW = _bind(_user32, "PostMessageW", w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
SendMessageW = _bind(_user32, "SendMessageW", LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
PostQuitMessage = _bind(_user32, "PostQuitMessage", None, c_int)
SetTimer = _bind(_user32, "SetTimer", w.UINT, w.HWND, w.UINT, w.UINT, c_void_p)
KillTimer = _bind(_user32, "KillTimer", w.BOOL, w.HWND, w.UINT)
FindWindowW = _bind(_user32, "FindWindowW", w.HWND, w.LPCWSTR, w.LPCWSTR)
RegisterWindowMessageW = _bind(_user32, "RegisterWindowMessageW", w.UINT, w.LPCWSTR)
RegisterHotKey = _bind(_user32, "RegisterHotKey", w.BOOL, w.HWND, c_int, w.UINT, w.UINT)
UnregisterHotKey = _bind(_user32, "UnregisterHotKey", w.BOOL, w.HWND, c_int)
ShowWindow = _bind(_user32, "ShowWindow", w.BOOL, w.HWND, c_int)
IsIconic = _bind(_user32, "IsIconic", w.BOOL, w.HWND)
SetForegroundWindow = _bind(_user32, "SetForegroundWindow", w.BOOL, w.HWND)
AllowSetForegroundWindow = _bind(_user32, "AllowSetForegroundWindow", w.BOOL, w.DWORD)
SetFocus = _bind(_user32, "SetFocus", w.HWND, w.HWND)
SetWindowPos = _bind(_user32, "SetWindowPos", w.BOOL, w.HWND, w.HWND, c_int, c_int, c_int, c_int, w.UINT)
GetWindowRect = _bind(_user32, "GetWindowRect", w.BOOL, w.HWND, POINTER(w.RECT))
GetClientRect = _bind(_user32, "GetClientRect", w.BOOL, w.HWND, POINTER(w.RECT))
GetDpiForWindow = _bind(_user32, "GetDpiForWindow", w.UINT, w.HWND)
GetCursorPos = _bind(_user32, "GetCursorPos", w.BOOL, POINTER(w.POINT))
MonitorFromPoint = _bind(_user32, "MonitorFromPoint", w.HANDLE, w.POINT, w.DWORD)
GetMonitorInfoW = _bind(_user32, "GetMonitorInfoW", w.BOOL, w.HANDLE, POINTER(MONITORINFO))
GetSystemMetrics = _bind(_user32, "GetSystemMetrics", c_int, c_int)
LoadCursorW = _bind(_user32, "LoadCursorW", w.HANDLE, w.HINSTANCE, c_void_p)
LoadImageW = _bind(_user32, "LoadImageW", w.HANDLE, w.HINSTANCE, w.LPCWSTR, w.UINT, c_int, c_int, w.UINT)
DestroyIcon = _bind(_user32, "DestroyIcon", w.BOOL, w.HICON)
CreatePopupMenu = _bind(_user32, "CreatePopupMenu", w.HMENU)
AppendMenuW = _bind(_user32, "AppendMenuW", w.BOOL, w.HMENU, w.UINT, c_ssize_t, w.LPCWSTR)
SetMenuDefaultItem = _bind(_user32, "SetMenuDefaultItem", w.BOOL, w.HMENU, w.UINT, w.UINT)
TrackPopupMenu = _bind(_user32, "TrackPopupMenu", c_int, w.HMENU, w.UINT, c_int, c_int, c_int, w.HWND, c_void_p)
DestroyMenu = _bind(_user32, "DestroyMenu", w.BOOL, w.HMENU)
GetKeyState = _bind(_user32, "GetKeyState", w.SHORT, c_int)
TrackMouseEvent = _bind(_user32, "TrackMouseEvent", w.BOOL, POINTER(TRACKMOUSEEVENT))
MessageBeep = _bind(_user32, "MessageBeep", w.BOOL, w.UINT)
DrawIconEx = _bind(_user32, "DrawIconEx", w.BOOL, w.HDC, c_int, c_int, w.HICON, c_int, c_int, w.UINT, w.HBRUSH, w.UINT)
GetWindowTextW = _bind(_user32, "GetWindowTextW", c_int, w.HWND, w.LPWSTR, c_int)
GetWindowTextLengthW = _bind(_user32, "GetWindowTextLengthW", c_int, w.HWND)
BeginPaint = _bind(_user32, "BeginPaint", w.HDC, w.HWND, POINTER(PAINTSTRUCT))
EndPaint = _bind(_user32, "EndPaint", w.BOOL, w.HWND, POINTER(PAINTSTRUCT))
InvalidateRect = _bind(_user32, "InvalidateRect", w.BOOL, w.HWND, c_void_p, w.BOOL)
FillRect = _bind(_user32, "FillRect", c_int, w.HDC, POINTER(w.RECT), w.HBRUSH)
DrawTextW = _bind(_user32, "DrawTextW", c_int, w.HDC, w.LPCWSTR, c_int, POINTER(w.RECT), w.UINT)
SetProcessDpiAwarenessContext = _bind(_user32, "SetProcessDpiAwarenessContext", w.BOOL, c_ssize_t)

CreateFontW = _bind(_gdi32, "CreateFontW", w.HFONT, c_int, c_int, c_int, c_int, c_int, w.DWORD, w.DWORD, w.DWORD,
                    w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.LPCWSTR)
CreateSolidBrush = _bind(_gdi32, "CreateSolidBrush", w.HBRUSH, w.COLORREF)
GetStockObject = _bind(_gdi32, "GetStockObject", w.HGDIOBJ, c_int)
RoundRect = _bind(_gdi32, "RoundRect", w.BOOL, w.HDC, c_int, c_int, c_int, c_int, c_int, c_int)
DeleteObject = _bind(_gdi32, "DeleteObject", w.BOOL, w.HGDIOBJ)
SelectObject = _bind(_gdi32, "SelectObject", w.HGDIOBJ, w.HDC, w.HGDIOBJ)
SetTextColor = _bind(_gdi32, "SetTextColor", w.COLORREF, w.HDC, w.COLORREF)
SetBkColor = _bind(_gdi32, "SetBkColor", w.COLORREF, w.HDC, w.COLORREF)
SetBkMode = _bind(_gdi32, "SetBkMode", c_int, w.HDC, c_int)
CreateCompatibleDC = _bind(_gdi32, "CreateCompatibleDC", w.HDC, w.HDC)
CreateCompatibleBitmap = _bind(_gdi32, "CreateCompatibleBitmap", w.HBITMAP, w.HDC, c_int, c_int)
BitBlt = _bind(_gdi32, "BitBlt", w.BOOL, w.HDC, c_int, c_int, c_int, c_int, w.HDC, c_int, c_int, w.DWORD)
DeleteDC = _bind(_gdi32, "DeleteDC", w.BOOL, w.HDC)

Shell_NotifyIconW = _bind(_shell32, "Shell_NotifyIconW", w.BOOL, w.DWORD, POINTER(NOTIFYICONDATAW))
ShellExecuteW = _bind(_shell32, "ShellExecuteW", w.HINSTANCE, w.HWND, w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, c_int)
SetAppUserModelID = _bind(_shell32, "SetCurrentProcessExplicitAppUserModelID", ctypes.HRESULT, w.LPCWSTR)
SHQueryUserNotificationState = _bind(_shell32, "SHQueryUserNotificationState", ctypes.HRESULT, POINTER(c_int))

HINSTANCE = GetModuleHandleW(None)


def set_window_rounded(hwnd):
    """Bo góc chuẩn Windows 11 (có khử răng cưa, do DWM vẽ)."""
    ctypes.WinDLL("dwmapi").DwmSetWindowAttribute(
        w.HWND(hwnd), DWMWA_WINDOW_CORNER_PREFERENCE, byref(c_int(DWMWCP_ROUND)), sizeof(c_int))


def register_session_notification(hwnd):
    ctypes.WinDLL("wtsapi32").WTSRegisterSessionNotification(w.HWND(hwnd), 0)


def user_is_available():
    """False khi đang chiếu slide hoặc chơi game toàn màn hình: không được bật popup đè lên."""
    state = c_int()
    SHQueryUserNotificationState(byref(state))
    return state.value in (QUNS_ACCEPTS_NOTIFICATIONS, QUNS_QUIET_TIME)


def colorref(value):
    """'#RRGGBB' -> COLORREF (0x00BBGGRR)."""
    return int(value[5:7] + value[3:5] + value[1:3], 16)


def low_word(value):
    return value & 0xFFFF


def high_word(value):
    return (value >> 16) & 0xFFFF


def signed_word(value):
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def register_window_class(name, procedure, style=0):
    info = WNDCLASSEXW()
    info.cbSize = sizeof(WNDCLASSEXW)
    info.style = style
    info.lpfnWndProc = procedure
    info.hInstance = HINSTANCE
    info.hCursor = LoadCursorW(None, IDC_ARROW)
    info.lpszClassName = name
    return RegisterClassExW(byref(info))


def acquire_mutex(name):
    """Giữ mutex suốt đời tiến trình. Trả về None nếu đã có instance khác."""
    handle = CreateMutexW(None, False, name)
    return None if ctypes.get_last_error() == ERROR_ALREADY_EXISTS else handle


def post_agent(message):
    """Gửi tín hiệu cho agent nếu nó đang chạy. Không chặn, chi phí gần như bằng 0."""
    hwnd = FindWindowW(AGENT_WINDOW_CLASS, None)
    return bool(hwnd) and bool(PostMessageW(hwnd, message, 0, 0))


def show_context_menu(hwnd, items, x, y):
    """items: (id, nhãn, checked, enabled); id=0 là đường kẻ. Trả về id được chọn hoặc 0."""
    menu = CreatePopupMenu()
    for item_id, label, checked, enabled in items:
        if not item_id:
            AppendMenuW(menu, MF_SEPARATOR, 0, None)
        else:
            flags = MF_STRING | (MF_CHECKED if checked else 0) | (0 if enabled else MF_GRAYED)
            AppendMenuW(menu, flags, item_id, label)
    SetForegroundWindow(hwnd)  # thiếu dòng này menu không tự đóng khi bấm ra ngoài
    chosen = TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_BOTTOMALIGN | TPM_RETURNCMD, x, y, 0, hwnd, None)
    PostMessageW(hwnd, WM_NULL, 0, 0)
    DestroyMenu(menu)
    return chosen
