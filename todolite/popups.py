"""Ba cửa sổ native của agent, vẽ bằng GDI nên không cần nạp giao diện nặng:

- QuickAdd: ô nhập nhanh hiện tức thì khi bấm Ctrl+Alt+T ở bất kỳ đâu.
- TimerPill: đồng hồ đếm ngược nổi của khối giờ hoặc Pomodoro, còn đó cả khi đã đóng cửa sổ chính.
- ReminderCard: thẻ nhắc việc có nút Xong, Báo lại, Mở; ở lại tới khi được xử lý.
"""
import winreg
from collections import namedtuple
from ctypes import byref, create_unicode_buffer
from ctypes import wintypes as w
from datetime import datetime

from . import APP_NAME
from .paths import FONT_PATHS, ICON_PATH
from .schedule import countdown, countdown_up, describe_event
from .win32 import *  # noqa: F403

HOTKEY_HINT = "Ví dụ: Nộp báo cáo mai 9h !1 #công-việc   ·   Enter lưu   ·   Esc đóng"
FONT_FAMILY = "Segoe UI Variable Text"
FONT_SEMIBOLD = "Segoe UI Variable Text Semibold"
FONT_ICONS = "Segoe Fluent Icons"
GLYPH_CLOSE = "\ue711"
SNOOZE_MINUTES = 10
EXTEND_MINUTES = 10
_fonts_loaded = False

# Thứ đồng hồ nổi đang đếm. kind: block | pomo; stamp đổi khi khối giờ hay phiên đổi, dùng để nhớ người dùng đã ẩn đồng hồ;
# rest: giờ nghỉ của Pomodoro, thanh tiến độ màu xanh lá.
PillItem = namedtuple("PillItem", "kind title start end stamp task_id rest")

# Cùng bảng màu với giao diện chính (ui/theme.py); agent không nạp được module đó vì nó cần CustomTkinter.
_LIGHT = {"bg": "#FFFFFF", "text": "#0A1324", "muted": "#46556E", "accent": "#1F5FE0", "track": "#D9E2F0",
          "on_accent": "#FFFFFF", "accent_hover": "#1A52C4", "track_hover": "#C6D3E8", "link": "#1456CC", "green": "#0B7342"}
_DARK = {"bg": "#0C1322", "text": "#F4F7FF", "muted": "#A9BAD6", "accent": "#1F6FEB", "track": "#1E2C47",
         "on_accent": "#FFFFFF", "accent_hover": "#1A60D0", "track_hover": "#2B3D60", "link": "#6CB6FF", "green": "#45E08A"}


def palette(theme):
    dark = theme == "dark"
    if theme == "system":
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                dark = winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
        except OSError:
            dark = False
    return {name: colorref(value) for name, value in (_DARK if dark else _LIGHT).items()}


def _load_fonts():
    """Nạp font đi kèm khi popup đầu tiên hiện: ngày nào không có popup thì agent không tốn gì. Lỗi thì giữ font Windows."""
    global _fonts_loaded, FONT_FAMILY, FONT_SEMIBOLD
    if not _fonts_loaded:
        _fonts_loaded = True
        if load_private_fonts(FONT_PATHS):
            FONT_FAMILY, FONT_SEMIBOLD = "Be Vietnam Pro", "Be Vietnam Pro SemiBold"


def _text_dpi(hwnd, store):
    """DPI dùng để tính cỡ popup: DPI màn hình nhân với tuỳ chọn Cỡ chữ, nên chữ và khung lớn cùng nhau."""
    _load_fonts()
    return GetDpiForWindow(hwnd) * float(store.setting("text_scale"))


def _font(size, dpi, family=None):
    height = -round(size * dpi / 72)
    return CreateFontW(height, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, family or FONT_FAMILY)


def _draw_text(dc, text, rect, color, flags):
    SetTextColor(dc, color)
    DrawTextW(dc, text, -1, byref(rect), flags | DT_SINGLELINE | DT_NOPREFIX | DT_VCENTER)


def _work_area(x, y):
    info = MONITORINFO()
    info.cbSize = sizeof(MONITORINFO)
    GetMonitorInfoW(MonitorFromPoint(w.POINT(x, y), MONITOR_DEFAULTTONEAREST), byref(info))
    return info.rcWork


class QuickAdd:
    CLASS = "TodoLiteQuickAdd"
    WIDTH, HEIGHT = 640, 96

    def __init__(self, agent):
        self.agent = agent
        self.hwnd = self.edit = None
        self.preview = ""
        self._procedure = WNDPROC(self._window_proc)
        register_window_class(self.CLASS, self._procedure, CS_DROPSHADOW)

    def show(self):
        if self.hwnd:
            SetForegroundWindow(self.hwnd)
            return
        self.colors = palette(self.agent.store.setting("theme"))
        self.preview = ""
        cursor = w.POINT()
        GetCursorPos(byref(cursor))
        area = _work_area(cursor.x, cursor.y)
        self.hwnd = CreateWindowExW(WS_EX_TOPMOST | WS_EX_TOOLWINDOW, self.CLASS, f"{APP_NAME} Quick Add", WS_POPUP,
                                    area.left, area.top, 1, 1, None, None, HINSTANCE, None)
        dpi = _text_dpi(self.hwnd, self.agent.store)
        self.scale = dpi / 96
        width, height = round(self.WIDTH * self.scale), round(self.HEIGHT * self.scale)
        x = (area.left + area.right - width) // 2
        y = area.top + (area.bottom - area.top) // 4
        SetWindowPos(self.hwnd, None, x, y, width, height, SWP_NOZORDER)
        set_window_rounded(self.hwnd)
        self.background = CreateSolidBrush(self.colors["bg"])
        self.input_font, self.hint_font = _font(14, dpi), _font(9.5, dpi)
        margin = round(18 * self.scale)
        self.edit = CreateWindowExW(0, "EDIT", "", WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL, margin, round(14 * self.scale),
                                    width - 2 * margin, round(34 * self.scale), self.hwnd, None, HINSTANCE, None)
        SendMessageW(self.edit, WM_SETFONT, self.input_font, 1)
        ShowWindow(self.hwnd, SW_SHOWNORMAL)
        SetForegroundWindow(self.hwnd)
        SetFocus(self.edit)

    def close(self):
        if self.hwnd:
            hwnd, self.hwnd, self.edit = self.hwnd, None, None
            DestroyWindow(hwnd)
            DeleteObject(self.background)
            DeleteObject(self.input_font)
            DeleteObject(self.hint_font)

    def _text(self):
        length = GetWindowTextLengthW(self.edit)
        buffer = create_unicode_buffer(length + 1)
        GetWindowTextW(self.edit, buffer, length + 1)
        return buffer.value

    def _update_preview(self):
        from .quickparse import describe, parse  # chỉ nạp regex khi thực sự dùng Quick Add
        text = self._text()
        self.preview = describe(parse(text), tag_label=self.agent.store.tag_label) if text.strip() else ""
        InvalidateRect(self.hwnd, None, False)

    def _submit(self):
        from .quickparse import parse
        text = self._text()
        if text.strip():
            fields = parse(text)
            self.agent.store.add_task(fields.pop("title"), **fields)
            self.agent.tick()
        self.close()

    def handle_key(self, message):
        """Gọi từ vòng lặp thông điệp. True nghĩa là phím đã được xử lý."""
        if not self.edit or message.hWnd != self.edit:
            return False
        if message.message == WM_CHAR and message.wParam == 0x7F:
            return True  # Ctrl+Backspace của ô EDIT cổ điển sinh ký tự rác
        if message.message != WM_KEYDOWN:
            return False
        if message.wParam == VK_RETURN:
            self._submit()
        elif message.wParam == VK_ESCAPE:
            self.close()
        elif message.wParam == VK_A and GetKeyState(VK_CONTROL) & 0x8000:
            SendMessageW(self.edit, EM_SETSEL, 0, -1)
        else:
            return False
        return True

    def _paint(self):
        paint = PAINTSTRUCT()
        dc = BeginPaint(self.hwnd, byref(paint))
        rect = w.RECT()
        GetClientRect(self.hwnd, byref(rect))
        FillRect(dc, byref(rect), self.background)
        margin = round(20 * self.scale)
        line = w.RECT(margin, round(54 * self.scale), rect.right - margin, round(84 * self.scale))
        SetBkMode(dc, TRANSPARENT)
        previous = SelectObject(dc, self.hint_font)
        if self.preview:
            _draw_text(dc, "→  " + self.preview, line, self.colors["link"], DT_LEFT | DT_END_ELLIPSIS)
        else:
            _draw_text(dc, HOTKEY_HINT, line, self.colors["muted"], DT_LEFT | DT_END_ELLIPSIS)
        SelectObject(dc, previous)
        EndPaint(self.hwnd, byref(paint))

    def _window_proc(self, hwnd, message, wparam, lparam):
        try:
            if message == WM_PAINT:
                self._paint()
                return 0
            if message == WM_ERASEBKGND:
                return 1
            if message == WM_CTLCOLOREDIT:
                SetTextColor(wparam, self.colors["text"])
                SetBkColor(wparam, self.colors["bg"])
                return self.background
            if message == WM_COMMAND and high_word(wparam) == EN_CHANGE:
                self._update_preview()
                return 0
            if message == WM_ACTIVATE and low_word(wparam) == 0 and self.hwnd == hwnd:
                PostMessageW(hwnd, WM_CLOSE, 0, 0)  # bấm ra ngoài thì đóng
                return 0
            if message == WM_CLOSE:
                self.close()
                return 0
        except Exception as error:
            self.agent.report(error)
        return DefWindowProcW(hwnd, message, wparam, lparam)


class TimerPill:
    CLASS = "TodoLiteTimerPill"
    WIDTH, HEIGHT = 280, 48
    TIMER_ID = 1
    MENU_EXTEND, MENU_FINISH, MENU_HIDE, MENU_PAUSE, MENU_SKIP, MENU_STOP = 1, 2, 3, 4, 5, 6

    def __init__(self, agent):
        self.agent = agent
        self.hwnd = None
        self.item = None
        self.hidden_stamp = None
        self._procedure = WNDPROC(self._window_proc)
        register_window_class(self.CLASS, self._procedure, CS_DBLCLKS | CS_DROPSHADOW)

    def sync(self, item):
        """item: PillItem đang đếm, hoặc None."""
        enabled = item is not None and self.agent.store.setting("timer_pill") == "1"
        if not enabled or item.stamp == self.hidden_stamp:
            self.item = None
            self._destroy()
            return
        self.item = item
        if self.hwnd:
            InvalidateRect(self.hwnd, None, False)
        else:
            self._create()

    def _position(self, width, height):
        saved = self.agent.store.setting("pill_pos")
        if saved:
            x, y = (int(part) for part in saved.split(","))
            if MonitorFromPoint(w.POINT(x + width // 2, y + height // 2), MONITOR_DEFAULTTONULL):
                return x, y
        area = _work_area(0, 0)
        gap = round(16 * self.scale)
        return area.right - width - gap, area.bottom - height - gap

    def _create(self):
        self.colors = palette(self.agent.store.setting("theme"))
        style = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        self.hwnd = CreateWindowExW(style, self.CLASS, f"{APP_NAME} Timer", WS_POPUP, 0, 0, 1, 1, None, None, HINSTANCE, None)
        dpi = _text_dpi(self.hwnd, self.agent.store)
        self.scale = dpi / 96
        width, height = round(self.WIDTH * self.scale), round(self.HEIGHT * self.scale)
        x, y = self._position(width, height)
        SetWindowPos(self.hwnd, None, x, y, width, height, SWP_NOZORDER | SWP_NOACTIVATE)
        set_window_rounded(self.hwnd)
        self.time_font, self.title_font = _font(14, dpi, FONT_SEMIBOLD), _font(9.5, dpi)
        self.brushes = {name: CreateSolidBrush(color) for name, color in self.colors.items()}
        ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        SetTimer(self.hwnd, self.TIMER_ID, 1000, None)

    def _destroy(self):
        if self.hwnd:
            hwnd, self.hwnd = self.hwnd, None
            KillTimer(hwnd, self.TIMER_ID)
            DestroyWindow(hwnd)
            DeleteObject(self.time_font)
            DeleteObject(self.title_font)
            for brush in self.brushes.values():
                DeleteObject(brush)

    def _paint(self):
        paint = PAINTSTRUCT()
        target = BeginPaint(self.hwnd, byref(paint))
        rect = w.RECT()
        GetClientRect(self.hwnd, byref(rect))
        # Vẽ vào bộ đệm rồi chép ra một lần để chữ số không nhấp nháy mỗi giây.
        dc = CreateCompatibleDC(target)
        bitmap = CreateCompatibleBitmap(target, rect.right, rect.bottom)
        old_bitmap = SelectObject(dc, bitmap)
        FillRect(dc, byref(rect), self.brushes["bg"])
        if self.item:
            self._draw_item(dc, rect)
        BitBlt(target, 0, 0, rect.right, rect.bottom, dc, 0, 0, SRCCOPY)
        SelectObject(dc, old_bitmap)
        DeleteObject(bitmap)
        DeleteDC(dc)
        EndPaint(self.hwnd, byref(paint))

    def _draw_item(self, dc, rect):
        item = self.item
        start, end = item.start, item.end
        now = datetime.now()
        left, gap = round(16 * self.scale), round(10 * self.scale)
        bar = round(3 * self.scale)
        SetBkMode(dc, TRANSPARENT)
        previous = SelectObject(dc, self.time_font)
        text = (countdown_up if item.kind == "pomo" else countdown)(end - now)  # cùng cách làm tròn với trang Pomodoro
        measure = w.RECT(0, 0, rect.right, rect.bottom - bar)
        DrawTextW(dc, text, -1, byref(measure), DT_SINGLELINE | DT_NOPREFIX | DT_CALCRECT)
        area = w.RECT(left, 0, left + measure.right, rect.bottom - bar)
        _draw_text(dc, text, area, self.colors["text"], DT_LEFT)
        SelectObject(dc, self.title_font)
        area = w.RECT(area.right + gap, 0, rect.right - left, rect.bottom - bar)
        _draw_text(dc, item.title, area, self.colors["muted"], DT_LEFT | DT_END_ELLIPSIS)
        SelectObject(dc, previous)
        total = max((end - start).total_seconds(), 1)
        remaining = min(max((end - now).total_seconds() / total, 0), 1)
        FillRect(dc, byref(w.RECT(0, rect.bottom - bar, rect.right, rect.bottom)), self.brushes["track"])
        FillRect(dc, byref(w.RECT(0, rect.bottom - bar, round(rect.right * remaining), rect.bottom)), self.brushes["green" if item.rest else "link"])

    def _on_timer(self):
        if self.item and datetime.now() >= self.item.end:
            self.agent.tick()
        elif self.hwnd:
            InvalidateRect(self.hwnd, None, False)

    def _save_position(self):
        rect = w.RECT()
        GetWindowRect(self.hwnd, byref(rect))
        self.agent.store.set_setting("pill_pos", f"{rect.left},{rect.top}")

    def _menu(self, x, y):
        item = self.item
        if not item:
            return
        if item.kind == "block":
            items = [(self.MENU_EXTEND, "Thêm 5 phút", False, True), (self.MENU_FINISH, "Kết thúc khối", False, True)]
        else:
            items = [(self.MENU_PAUSE, "Tạm dừng", False, True), (self.MENU_SKIP, "Bỏ qua phiên này", False, True),
                     (self.MENU_STOP, "Dừng Pomodoro", False, True)]
        chosen = show_context_menu(self.hwnd, items + [(0, "", False, True), (self.MENU_HIDE, "Ẩn đồng hồ", False, True)], x, y)
        store = self.agent.store
        if chosen == self.MENU_EXTEND:
            store.extend_block(item.task_id, 5)
        elif chosen == self.MENU_FINISH:
            store.end_block(item.task_id)
        elif chosen in (self.MENU_PAUSE, self.MENU_SKIP, self.MENU_STOP):
            from . import pomodoro
            if chosen == self.MENU_PAUSE:
                pomodoro.pause(store, datetime.now())
            else:
                (pomodoro.skip if chosen == self.MENU_SKIP else pomodoro.stop)(store)
        elif chosen == self.MENU_HIDE:
            self.hidden_stamp = item.stamp
        if chosen:
            self.agent.tick()

    def _window_proc(self, hwnd, message, wparam, lparam):
        try:
            if message == WM_PAINT:
                self._paint()
                return 0
            if message == WM_ERASEBKGND:
                return 1
            if message == WM_TIMER:
                self._on_timer()
                return 0
            if message == WM_NCHITTEST:
                return HTCAPTION  # kéo ở đâu cũng di chuyển được
            if message == WM_EXITSIZEMOVE:
                self._save_position()
                return 0
            if message == WM_NCLBUTTONDBLCLK:
                self.agent.open_page("pomodoro" if self.item and self.item.kind == "pomo" else "dashboard")
                return 0
            if message == WM_NCRBUTTONUP:
                self._menu(signed_word(lparam), signed_word(lparam >> 16))
                return 0
        except Exception as error:
            self.agent.report(error)
        return DefWindowProcW(hwnd, message, wparam, lparam)


class ReminderCard:
    """Thẻ nhắc việc có nút bấm, vẽ ngay trong agent nên bấm là xử lý tức thì.

    Không dùng nút trên toast: Windows 11 mới chặn URI tuỳ chỉnh gọi từ toast bằng hộp thoại
    chọn ứng dụng. Nhiều nhắc cùng lúc thì xếp hàng, xử lý xong thẻ này mới hiện thẻ sau.
    """
    CLASS = "TodoLiteReminderCard"
    WIDTH, HEIGHT = 384, 136
    CLOSE = "close"

    def __init__(self, agent):
        self.agent = agent
        self.hwnd = None
        self.queue = []  # [(task_id, loại mốc)]
        self.task = None
        self.kind = ""
        self.heading = self.detail = ""
        self.targets = []  # [(hành động, nhãn, RECT)]
        self.hover = None
        self.tracking = False
        self._procedure = WNDPROC(self._window_proc)
        register_window_class(self.CLASS, self._procedure, CS_DROPSHADOW)

    def push(self, task_id, kind, now):
        self.queue = [item for item in self.queue if item[0] != task_id] + [(task_id, kind)]
        MessageBeep(MB_ICONASTERISK)
        self.refresh(now)

    def refresh(self, now):
        """Bỏ việc đã xong khỏi hàng đợi và cập nhật chữ theo thời gian thật."""
        self.task = None
        while self.queue:
            task_id, kind = self.queue[0]
            task = self.agent.store.get_task(task_id)
            if task and not task["done_at"]:
                self.task, self.kind = task, kind
                break
            self.queue.pop(0)
        if self.task is None:
            self._destroy()
            return
        self.heading, self.detail = describe_event(self.task, self.kind, now)
        if self.hwnd:
            self._layout()
            InvalidateRect(self.hwnd, None, False)
        else:
            self._create()

    def _actions(self):
        second = ("extend", f"Thêm {EXTEND_MINUTES} phút") if self.kind == "block_end" else ("snooze", f"Báo lại {SNOOZE_MINUTES} phút")
        return [("done", "Xong", 92), (*second, 132), ("open", "Mở", 64)]

    def _layout(self):
        scale = self.scale
        client = w.RECT()
        GetClientRect(self.hwnd, byref(client))
        left = round(16 * scale)
        top, bottom = round(92 * scale), round(122 * scale)
        self.targets = []
        for action, label, width in self._actions():
            right = left + round(width * scale)
            self.targets.append((action, label, w.RECT(left, top, right, bottom)))
            left = right + round(8 * scale)
        size = round(28 * scale)
        inset = round(8 * scale)
        self.close_rect = w.RECT(client.right - size - inset, inset, client.right - inset, inset + size)

    def _create(self):
        self.colors = palette(self.agent.store.setting("theme"))
        style = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        self.hwnd = CreateWindowExW(style, self.CLASS, f"{APP_NAME} Reminder", WS_POPUP, 0, 0, 1, 1, None, None, HINSTANCE, None)
        dpi = _text_dpi(self.hwnd, self.agent.store)
        self.scale = dpi / 96
        width, height = round(self.WIDTH * self.scale), round(self.HEIGHT * self.scale)
        area = _work_area(0, 0)
        gap = round(16 * self.scale)
        bottom = area.bottom - gap
        pill = self.agent.pill
        if pill.hwnd:  # chừa chỗ cho đồng hồ nổi ở vị trí mặc định
            bottom -= round(pill.HEIGHT * self.scale) + gap
        SetWindowPos(self.hwnd, None, area.right - width - gap, bottom - height, width, height, SWP_NOZORDER | SWP_NOACTIVATE)
        set_window_rounded(self.hwnd)
        self.fonts = {"small": _font(9, dpi), "title": _font(11.5, dpi, FONT_SEMIBOLD), "body": _font(9.5, dpi),
                      "button": _font(9.5, dpi, FONT_SEMIBOLD), "glyph": _font(8, dpi, FONT_ICONS)}
        self.brushes = {name: CreateSolidBrush(color) for name, color in self.colors.items()}
        icon_size = round(20 * self.scale)
        self.icon = LoadImageW(None, ICON_PATH, IMAGE_ICON, icon_size, icon_size, LR_LOADFROMFILE)
        self._layout()
        ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)

    def _destroy(self):
        if self.hwnd:
            hwnd, self.hwnd = self.hwnd, None
            DestroyWindow(hwnd)
            DestroyIcon(self.icon)
            for handle in (*self.fonts.values(), *self.brushes.values()):
                DeleteObject(handle)
            self.hover = None
            self.tracking = False

    def _paint(self):
        paint = PAINTSTRUCT()
        target = BeginPaint(self.hwnd, byref(paint))
        rect = w.RECT()
        GetClientRect(self.hwnd, byref(rect))
        dc = CreateCompatibleDC(target)
        bitmap = CreateCompatibleBitmap(target, rect.right, rect.bottom)
        old_bitmap = SelectObject(dc, bitmap)
        FillRect(dc, byref(rect), self.brushes["bg"])
        self._draw(dc, rect)
        BitBlt(target, 0, 0, rect.right, rect.bottom, dc, 0, 0, SRCCOPY)
        SelectObject(dc, old_bitmap)
        DeleteObject(bitmap)
        DeleteDC(dc)
        EndPaint(self.hwnd, byref(paint))

    def _draw(self, dc, rect):
        scale, colors = self.scale, self.colors
        left, right = round(16 * scale), rect.right - round(16 * scale)
        SetBkMode(dc, TRANSPARENT)
        DrawIconEx(dc, left, round(13 * scale), self.icon, round(20 * scale), round(20 * scale), 0, None, DI_NORMAL)
        previous = SelectObject(dc, self.fonts["small"])
        label = APP_NAME if len(self.queue) < 2 else f"{APP_NAME}  ·  còn {len(self.queue) - 1} nhắc nữa"
        _draw_text(dc, label, w.RECT(left + round(28 * scale), round(12 * scale), self.close_rect.left, round(34 * scale)),
                   colors["muted"], DT_LEFT)
        if self.hover == self.CLOSE:
            FillRect(dc, byref(self.close_rect), self.brushes["track"])
        SelectObject(dc, self.fonts["glyph"])
        _draw_text(dc, GLYPH_CLOSE, self.close_rect, colors["muted"], DT_CENTER)
        SelectObject(dc, self.fonts["title"])
        _draw_text(dc, self.heading, w.RECT(left, round(38 * scale), right, round(62 * scale)), colors["text"], DT_LEFT | DT_END_ELLIPSIS)
        SelectObject(dc, self.fonts["body"])
        _draw_text(dc, self.detail, w.RECT(left, round(62 * scale), right, round(84 * scale)), colors["muted"], DT_LEFT | DT_END_ELLIPSIS)
        SelectObject(dc, self.fonts["button"])
        pen = SelectObject(dc, GetStockObject(NULL_PEN))
        corner = round(8 * scale)
        for action, text, area in self.targets:
            primary = action == "done"
            shade = ("accent_hover" if self.hover == action else "accent") if primary else ("track_hover" if self.hover == action else "track")
            brush = SelectObject(dc, self.brushes[shade])
            RoundRect(dc, area.left, area.top, area.right + 1, area.bottom + 1, corner, corner)
            SelectObject(dc, brush)
            _draw_text(dc, text, area, colors["on_accent" if primary else "text"], DT_CENTER)
        SelectObject(dc, pen)
        SelectObject(dc, previous)

    def _hit(self, x, y):
        for action, _, area in self.targets:
            if area.left <= x < area.right and area.top <= y < area.bottom:
                return action
        area = self.close_rect
        return self.CLOSE if area.left <= x < area.right and area.top <= y < area.bottom else None

    def _on_mouse_move(self, x, y):
        if not self.tracking:
            event = TRACKMOUSEEVENT(sizeof(TRACKMOUSEEVENT), TME_LEAVE, self.hwnd, 0)
            self.tracking = bool(TrackMouseEvent(byref(event)))
        hover = self._hit(x, y)
        if hover != self.hover:
            self.hover = hover
            InvalidateRect(self.hwnd, None, False)

    def _on_click(self, x, y):
        action = self._hit(x, y)
        if not action or not self.task:
            return
        store, task_id = self.agent.store, self.task["id"]
        self.queue.pop(0)
        self.hover = None
        if action == "done":
            store.complete_task(task_id)
        elif action == "snooze":
            store.snooze(task_id, SNOOZE_MINUTES)
        elif action == "extend":
            store.extend_block(task_id, EXTEND_MINUTES)
        elif action == "open":
            self.agent.open_task(task_id)
        self.agent.tick()

    def _window_proc(self, hwnd, message, wparam, lparam):
        try:
            if message == WM_PAINT:
                self._paint()
                return 0
            if message == WM_ERASEBKGND:
                return 1
            if message == WM_MOUSEACTIVATE:
                return MA_NOACTIVATE  # bấm nút không cướp focus khỏi cửa sổ đang làm việc
            if message == WM_MOUSEMOVE:
                self._on_mouse_move(signed_word(lparam), signed_word(lparam >> 16))
                return 0
            if message == WM_MOUSELEAVE:
                self.tracking = False
                self.hover = None
                InvalidateRect(hwnd, None, False)
                return 0
            if message == WM_LBUTTONUP:
                self._on_click(signed_word(lparam), signed_word(lparam >> 16))
                return 0
        except Exception as error:
            self.agent.report(error)
        return DefWindowProcW(hwnd, message, wparam, lparam)
