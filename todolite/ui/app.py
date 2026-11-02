"""Cửa sổ chính. Tiến trình này chỉ sống khi cửa sổ mở: đóng là trả toàn bộ RAM cho hệ thống."""
import ctypes
import time
from ctypes import byref, c_int, sizeof
from ctypes import wintypes as w
from datetime import date, datetime

import customtkinter as ctk
from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import AppearanceModeTracker
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from .. import APP_ID, APP_NAME
from ..db import Store
from ..paths import ICON_PATH
from ..schedule import ALL_DAY_TIME, countdown_up, from_text
from ..win32 import (MONITOR_DEFAULTTONEAREST, MONITOR_DEFAULTTONULL, SW_RESTORE, UI_WINDOW_CLASS, WM_APP_DATA, FindWindowW, GetCurrentProcess, IsIconic,
                     K32EmptyWorkingSet, MonitorFromPoint, SetAppUserModelID, SetForegroundWindow, ShowWindow, acquire_mutex, colorref,
                     keep_content_on_resize, post_agent)
from . import motion, theme
from .pages import Dashboard, SettingsPage, TasksPage
from .sidebar import Sidebar
from .theme import BG, RAIL, resolve
from .widgets import Snackbar

UI_MUTEX = "Local\\TodoLite.UI"
DEFAULT_SIZE = "1200x780"
MIN_WIDTH, MIN_HEIGHT = 960, 640
DWMWA_CAPTION_COLOR = 35
GA_ROOT = 2
SHORTCUT_PAGES = ("dashboard", "calendar", "almanac", "pomodoro", "today", "upcoming", "all", "done")
OWN_PAGES = ("dashboard", "calendar", "almanac", "pomodoro", "settings")
RESIZE_SETTLE_MS = 150
DPI_POLL_SECONDS = 5
THEME_POLL_MS = 2000
POMODORO_GRACE = 3  # giây: agent chuyển phiên đúng lúc hết giờ; quá chừng này mà chưa ai chuyển (agent không chạy) thì cửa sổ tự chuyển
_user32 = ctypes.WinDLL("user32")  # bản riêng, không đụng restype của windll.user32 mà CustomTkinter dùng chung
_user32.MonitorFromWindow.restype = w.HANDLE
_user32.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
_theme_update = AppearanceModeTracker.update.__func__


def _follow_system_theme(cls):
    """CustomTkinter dò theme mỗi giây suốt đời app. Chỉ cần dò khi người dùng chọn theo hệ thống, theme cố định thì vòng dừng
    hẳn và App.set_theme mở lại khi cần."""
    if cls.appearance_mode_set_by == "system":
        _theme_update(cls)
    else:
        cls.update_loop_running = False


AppearanceModeTracker.update = classmethod(_follow_system_theme)
AppearanceModeTracker.update_loop_interval = THEME_POLL_MS
ScalingTracker.check_dpi_scaling = classmethod(lambda cls: None)  # vòng dò DPI mỗi giây, App tự dò khi đổi màn hình, xem _check_dpi


def calendar_page(master, app):
    from .calendar import CalendarPage  # nạp khi mở lần đầu để cửa sổ hiện nhanh hơn
    return CalendarPage(master, app)


def almanac_page(master, app):
    from .almanac_page import AlmanacPage
    return AlmanacPage(master, app)


def pomodoro_page(master, app):
    from .pomodoro_page import PomodoroPage
    return PomodoroPage(master, app)


class App(ctk.CTk):
    monitor = None  # Tk có thể gửi Configure trước khi __init__ chạy xong
    dpi_checked = 0.0

    def __init__(self):
        super().__init__(fg_color=BG)
        self.store = Store()
        theme.init_fonts()
        self.title(APP_NAME)
        self.iconbitmap(ICON_PATH)
        self.animator = motion.install(self)
        self._apply_text_scale()
        self._restore_geometry()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.pages = {}
        self.current_page = None
        self.current_key = None
        self.tag_colors = {}
        self.minute = None
        self.stats = None
        self.pomodoro_end = None  # giờ hết phiên Pomodoro đang chạy, đọc lại mỗi lần dữ liệu đổi
        self.window_size = None
        self.settle_job = None
        self.resting = False
        self.version = self.store.data_version()
        self._load_tag_colors()
        self.sidebar = Sidebar(self, self.navigate)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_propagate(False)  # cỡ vùng nội dung do cửa sổ quyết định, xem _hold_layout
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self._snackbar = None
        self.fade = motion.CrossFade(self, self.content)
        self.sidebar.slide.wait = lambda: self.fade.holding

        self.bind("<Control-n>", lambda _: self._focus_quick())
        self.bind("<Control-f>", lambda _: self._focus_search())
        self.bind("<Escape>", lambda _: self.close_editor())
        for number, key in enumerate(SHORTCUT_PAGES, start=1):
            self.bind(f"<Control-Key-{number}>", lambda _event, target=key: self.navigate(target))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.navigate("dashboard")
        self._handle_request()
        self.after(50, self._prepare_window)
        self.tick_job = self.after(1000, self._tick)
        self.bindtags(("TodoLiteWindow", *self.bindtags()))  # thẻ riêng của cửa sổ: <Map> của hàng trăm widget con không gọi tới
        self.bind_class("TodoLiteWindow", "<Map>", self._on_map)

    # ---------- Khung cửa sổ ----------

    def _windows_set_titlebar_color(self, color_mode):
        """Thanh tiêu đề luôn tối để nút cửa sổ có màu sáng trên khung xanh đen, ở cả theme sáng."""
        super()._windows_set_titlebar_color("dark")

    def _restore_geometry(self):
        saved = self.store.setting("window")
        if saved:
            size, _, position = saved.partition("+")
            x, _, y = position.partition("+")
            visible = x and MonitorFromPoint(w.POINT(int(x) + 200, int(y) + 40), MONITOR_DEFAULTTONULL)
            self.geometry(saved if visible else size)
        else:
            self.geometry(DEFAULT_SIZE)

    def _prepare_window(self):
        keep_content_on_resize(ctypes.windll.user32.GetAncestor(self.winfo_id(), GA_ROOT))
        keep_content_on_resize(self.winfo_id())
        self.apply_caption_color()

    def _apply_text_scale(self):
        """Cỡ chữ phóng to cả bố cục, nên cửa sổ tối thiểu cũng lớn theo, nhưng không vượt quá màn hình."""
        scale = float(self.store.setting("text_scale"))
        if scale != ScalingTracker.widget_scaling:
            ctk.set_widget_scaling(scale)
        window_scale = ScalingTracker.get_window_scaling(self)
        self.minsize(min(round(MIN_WIDTH * scale), round(self.winfo_screenwidth() * 0.95 / window_scale)),
                     min(round(MIN_HEIGHT * scale), round(self.winfo_screenheight() * 0.9 / window_scale)))

    def set_text_scale(self, value):
        with self.fade(self):  # cả thanh bên cũng phóng to theo
            self.store.set_setting("text_scale", value)
            self._apply_text_scale()
            self.refresh()

    def apply_caption_color(self):
        """Tô thanh tiêu đề cùng màu khung để cửa sổ liền mạch trên Windows 11."""
        hwnd = ctypes.windll.user32.GetAncestor(self.winfo_id(), GA_ROOT)
        color = c_int(colorref(resolve(RAIL)))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(w.HWND(hwnd), DWMWA_CAPTION_COLOR, byref(color), sizeof(color))

    def _update_dimensions_event(self, event=None):
        """CustomTkinter nhận sự kiện của mọi widget con ở đây, còn cửa sổ thì chỉ cần sự kiện của chính nó."""
        if event is not None and event.widget is self:
            super()._update_dimensions_event(event)
            self._on_resize((event.width, event.height))
            monitor = _user32.MonitorFromWindow(self.winfo_id(), MONITOR_DEFAULTTONEAREST)
            if monitor != self.monitor:  # kéo sang màn hình khác
                self.monitor = monitor
                self._check_dpi()

    def _check_dpi(self):
        """Thay vòng dò DPI mỗi giây của CustomTkinter: dò khi cửa sổ sang màn hình khác, và thưa thớt trong nhịp chung để bắt
        lúc người dùng đổi tỉ lệ hiển thị của Windows."""
        self.dpi_checked = time.monotonic()
        if self.state() == "iconic":
            return
        scale = ScalingTracker.get_window_dpi_scaling(self)
        if scale != ScalingTracker.window_dpi_scaling_dict.get(self):
            ScalingTracker.window_dpi_scaling_dict[self] = scale
            self.attributes("-alpha", 0.15)
            self.block_update_dimensions_event()
            ScalingTracker.update_scaling_callbacks_for_window(self)
            self.unblock_update_dimensions_event()
            self.attributes("-alpha", 1)

    def set_theme(self, value):
        ctk.set_appearance_mode(value)
        if value == "system" and not AppearanceModeTracker.update_loop_running:
            AppearanceModeTracker.update_loop_running = True
            self.after(AppearanceModeTracker.update_loop_interval, AppearanceModeTracker.update)

    def _on_resize(self, size):
        previous, self.window_size = self.window_size, size
        if previous is None or previous == size or self.state() != "normal" or not self.content.winfo_ismapped():
            return
        self.fade.cancel()
        if self.settle_job:
            self.after_cancel(self.settle_job)
        else:
            self._hold_layout()
        self.settle_job = self.after(RESIZE_SETTLE_MS, self._release_layout)

    def _hold_layout(self):
        """Mỗi bước kéo giãn, Tk phải dời và vẽ lại hàng trăm cửa sổ con nên rất giật. Trong lúc kéo, bố cục
        giữ nguyên cỡ và cửa sổ chỉ để lộ thêm nền, thả tay mới sắp xếp lại một lần."""
        self.grid_columnconfigure(1, weight=0, minsize=self.content.winfo_width())
        self.grid_rowconfigure(0, weight=0, minsize=self.content.winfo_height())

    def _release_layout(self):
        self.settle_job = None
        self.grid_columnconfigure(1, weight=1, minsize=0)
        self.grid_rowconfigure(0, weight=1, minsize=0)

    def _on_close(self):
        editor = self._open_editor()
        if editor:
            editor.flush()
        scale = ScalingTracker.get_window_scaling(self)
        width, height = round(self.winfo_width() / scale), round(self.winfo_height() / scale)
        if self.state() == "normal":
            self.store.set_setting("window", f"{width}x{height}+{self.winfo_x()}+{self.winfo_y()}")
        self.destroy()

    def destroy(self):
        self.fade.cancel()
        self.animator.stop()
        super().destroy()

    def _load_tag_colors(self):
        rows = self.store.tags()
        self.tag_colors = {row["name"]: row["color"] for row in rows}
        return rows

    def tag_color(self, name):
        return self.tag_colors.get(name, theme.TAG_FALLBACK)

    # ---------- Điều hướng ----------

    def _page(self, name):
        """Trang chỉ được dựng khi mở lần đầu, giúp cửa sổ hiện nhanh hơn."""
        if name not in self.pages:
            factory = {"dashboard": Dashboard, "calendar": calendar_page, "almanac": almanac_page, "pomodoro": pomodoro_page, "tasks": TasksPage,
                       "settings": SettingsPage}[name]
            self.pages[name] = factory(self.content, self)
            self.pages[name].grid(row=0, column=0, sticky="nsew")
        return self.pages[name]

    def navigate(self, key):
        """Đổi trang ngay trong lần gọi này, lớp phủ chỉ mờ đi sau đó nên các luồng gọi navigate rồi đọc trang vẫn đúng."""
        with self.fade(when=key != self.current_key):
            self._navigate(key)

    def _navigate(self, key):
        editor = self._open_editor()
        if editor:
            editor.flush()
        if key in OWN_PAGES:
            page = self._page(key)
        else:
            page = self._page("tasks")
            if key.startswith("tag:"):
                tag_id = int(key[4:])
                name = next((row["name"] for row in self.store.tags() if row["id"] == tag_id), "")
                page.show_view("all", tag_id, name)
            else:
                page.show_view(key)
            page.close_editor()
        if page is not self.current_page:
            if self.current_page is not None:
                self.current_page.grid_remove()
            page.grid()
            self.current_page = page
        self.current_key = key
        self.sidebar.set_active(key)
        self.refresh()
        if self._snackbar is not None:
            self._snackbar.lift()

    @property
    def snackbar(self):
        """Dựng khi cần lần đầu: phần lớn phiên mở cửa sổ không hiện thông báo nào."""
        if self._snackbar is None:
            self._snackbar = Snackbar(self.content)
        return self._snackbar

    def open_task(self, task_id):
        task = self.store.get_task(task_id)
        if task is None:
            return
        view = "done" if task["done_at"] else "all"
        with self.fade():  # đổi trang và mở panel là một lần chuyển cảnh
            self.navigate(view)
            self.pages["tasks"].open_editor(task_id)

    def _open_editor(self):
        page = self.current_page
        return page.editor if getattr(page, "editor_open", False) else None

    def close_editor(self):
        if hasattr(self.current_page, "close_editor"):
            self.current_page.close_editor()

    def _focus_quick(self):
        if not hasattr(self.current_page, "quick"):  # Cài đặt và Pomodoro không có ô thêm việc
            self.navigate("dashboard")
        self.current_page.quick.focus_entry()

    def _focus_search(self):
        if "tasks" not in self.pages or self.current_page is not self.pages["tasks"]:
            self.navigate("all")
        self.pages["tasks"].search.focus_set()

    # ---------- Dữ liệu ----------

    def refresh(self):
        now = datetime.now()
        self.minute = now.minute
        self.version = self.store.data_version()
        self.stats = stats = self.store.stats(now)
        side = self.sidebar
        side.set_count("today", stats["today_open"] + stats["overdue"])
        side.set_count("upcoming", stats["upcoming"])
        side.set_count("all", stats["open_total"])
        side.set_tags(self._load_tag_colors())
        end = self.store.setting("pomo_end")
        self.pomodoro_end = from_text(end) if end else None
        self._show_pomodoro(now)
        if self.current_page is not None and hasattr(self.current_page, "refresh"):
            self.current_page.refresh(now)

    def changed(self, reload_editor=True):
        """Gọi sau mỗi lần ghi dữ liệu: báo agent tính lại lịch rồi vẽ lại giao diện."""
        post_agent(WM_APP_DATA)
        self.refresh()
        editor = self._open_editor()
        if reload_editor and editor:
            editor.reload()

    def add_task(self, fields):
        title = fields.pop("title")
        tasks = self.pages.get("tasks")
        on_tasks_page = tasks is not None and self.current_page is tasks
        if on_tasks_page and tasks.tag_name:
            fields["tags"] = [*fields["tags"], tasks.tag_name]
        wants_today = not on_tasks_page or tasks.view == "today"
        if wants_today and not fields["due_at"]:
            fields["due_at"], fields["all_day"] = f"{date.today().isoformat()} {ALL_DAY_TIME}", 1
        self.store.add_task(title, **fields)
        self.changed()

    def toggle_task(self, task):
        task_id = task["id"]
        current = self.store.get_task(task_id)
        if current is None:
            return
        if current["done_at"]:
            self.store.reopen_task(task_id)
            self.snackbar.show(f"Đã mở lại: {current['title']}")
        else:
            self.store.complete_task(task_id)
            self.snackbar.show(f"Đã xong: {current['title']}", "Hoàn tác", lambda: self._undo_complete(task_id))
        self.changed()

    def _undo_complete(self, task_id):
        self.store.reopen_task(task_id)
        self.changed()

    # ---------- Nhịp 1 giây ----------

    def _handle_request(self):
        request = self.store.take_ui_request()
        if request.startswith("task:"):
            self.open_task(int(request[5:]))
        elif request.startswith("page:") and request[5:] in OWN_PAGES:
            self.navigate(request[5:])

    def _show_pomodoro(self, now):
        """Đồng hồ Pomodoro đang chạy hiện ngay trên thanh bên, ở trang nào cũng thấy. Hết giờ mà agent không chuyển phiên (agent
        không chạy) thì tự chuyển, để đồng hồ không đứng ở 00:00."""
        end = self.pomodoro_end
        if end is None:
            self.sidebar.set_count("pomodoro", "")
            return
        self.sidebar.set_count("pomodoro", countdown_up(end - now))
        if (now - end).total_seconds() > POMODORO_GRACE:
            from .. import pomodoro
            self.pomodoro_end = None
            pomodoro.complete_due(self.store, now)
            self.changed()

    def _tick(self):
        """Chỉ cập nhật đồng hồ đếm ngược; dữ liệu do tiến trình khác đổi được phát hiện qua data_version."""
        self.tick_job = None
        now = datetime.now()
        try:
            if self.state() == "iconic":
                self._rest()
                return  # không ai nhìn thấy: nhịp dừng hẳn, cửa sổ hiện lại thì _on_map chạy lại
            self.resting = False
            if time.monotonic() - self.dpi_checked >= DPI_POLL_SECONDS:
                self._check_dpi()
            version = self.store.data_version()
            if version != self.version:
                self.version = version
                self._handle_request()
                self.refresh()
                editor = self._open_editor()
                if editor:
                    editor.reload()
            elif now.minute != self.minute:
                self.refresh()
            else:
                self._show_pomodoro(now)
                if hasattr(self.current_page, "tick"):
                    self.current_page.tick(now)
        finally:
            if not self.resting:
                self.tick_job = self.after(1005 - datetime.now().microsecond // 1000, self._tick)  # đầu giây kế tiếp, đồng hồ nhảy đều

    def _on_map(self, _event):
        if self.tick_job is None:
            self._tick()

    def _rest(self):
        """Thu nhỏ xuống thanh tác vụ thì trả RAM vật lý cho hệ thống, Windows tự nạp lại khi cần."""
        if not self.resting:
            self.resting = True
            K32EmptyWorkingSet(GetCurrentProcess())


def _bring_existing_to_front():
    hwnd = FindWindowW(UI_WINDOW_CLASS, APP_NAME)
    if hwnd:
        if IsIconic(hwnd):
            ShowWindow(hwnd, SW_RESTORE)
        SetForegroundWindow(hwnd)


def run():
    mutex = acquire_mutex(UI_MUTEX)
    if mutex is None:
        _bring_existing_to_front()
        return
    SetAppUserModelID(APP_ID)
    store = Store()
    ctk.set_appearance_mode(store.setting("theme"))
    store.close()
    App().mainloop()
