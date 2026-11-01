"""Cửa sổ chính. Tiến trình này chỉ sống khi cửa sổ mở: đóng là trả toàn bộ RAM cho hệ thống."""
import ctypes
from ctypes import byref, c_int, sizeof
from ctypes import wintypes as w
from datetime import date, datetime

import customtkinter as ctk
from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import AppearanceModeTracker
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from .. import APP_ID, APP_NAME
from ..db import Store
from ..paths import ICON_PATH
from ..schedule import ALL_DAY_TIME
from ..win32 import (MONITOR_DEFAULTTONULL, SW_RESTORE, UI_WINDOW_CLASS, WM_APP_DATA, FindWindowW, IsIconic, MonitorFromPoint,
                     SetAppUserModelID, SetForegroundWindow, ShowWindow, acquire_mutex, colorref, post_agent)
from . import theme
from .calendar import CalendarPage
from .pages import Dashboard, SettingsPage, TasksPage
from .theme import ACCENT, BG, CARD_HOVER, FILL, Icon, MUTED, ON_FILL, SIDEBAR, TEXT, resolve, tag_edge
from .widgets import Snackbar

UI_MUTEX = "Local\\TodoLite.UI"
DEFAULT_SIZE = "1200x780"
MIN_WIDTH, MIN_HEIGHT = 960, 640
DWMWA_CAPTION_COLOR = 35
GA_ROOT = 2
SHORTCUT_PAGES = ("dashboard", "calendar", "almanac", "today", "upcoming", "all", "done")


def almanac_page(master, app):
    from .almanac_page import AlmanacPage  # nạp khi mở lần đầu để cửa sổ hiện nhanh hơn
    return AlmanacPage(master, app)


class NavItem(ctk.CTkFrame):
    def __init__(self, master, glyph, label, command, height=38, glyph_color=MUTED, glyph_size=15):
        super().__init__(master, fg_color="transparent", corner_radius=8, height=height)
        self.command = command
        self.active = False
        self.glyph_color = glyph_color
        self.pack_propagate(False)
        self.glyph = ctk.CTkLabel(self, text=glyph, width=22, font=theme.icon(glyph_size), text_color=glyph_color)
        self.glyph.pack(side="left", padx=(10, 8))
        self.label = ctk.CTkLabel(self, text=label, font=theme.text(14), text_color=TEXT, anchor="w")
        self.label.pack(side="left", fill="x", expand=True)
        self.count = ctk.CTkLabel(self, text="", font=theme.text(12), text_color=MUTED, width=24)
        self.count.pack(side="right", padx=(0, 8))
        for widget in (self, self.glyph, self.label, self.count):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<Button-1>", lambda _: self.command())

    def _on_enter(self, _event):
        if not self.active:
            self.configure(fg_color=CARD_HOVER)

    def _on_leave(self, _event):
        if not self.active:
            self.configure(fg_color="transparent")

    def set_active(self, active):
        self.active = active
        self.configure(fg_color=FILL if active else "transparent")
        self.glyph.configure(text_color=ON_FILL if active else self.glyph_color)
        self.label.configure(text_color=ON_FILL if active else TEXT)
        self.count.configure(text_color=ON_FILL if active else MUTED)

    def set_count(self, value):
        self.count.configure(text=str(value) if value else "")


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.store = Store()
        theme.init_fonts()
        self.title(APP_NAME)
        self.iconbitmap(ICON_PATH)
        self.minsize(MIN_WIDTH, MIN_HEIGHT)
        self._restore_geometry()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.pages = {}
        self.current_page = None
        self.current_key = None
        self.tag_items = {}
        self.tag_signature = None
        self.tag_colors = {}
        self.minute = None
        self.version = self.store.data_version()
        self._load_tag_colors()
        self._build_sidebar()
        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.snackbar = Snackbar(self.content)

        self.bind("<Control-n>", lambda _: self._focus_quick())
        self.bind("<Control-f>", lambda _: self._focus_search())
        self.bind("<Escape>", lambda _: self.close_editor())
        for number, key in enumerate(SHORTCUT_PAGES, start=1):
            self.bind(f"<Control-Key-{number}>", lambda _event, target=key: self.navigate(target))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.navigate("dashboard")
        self._handle_request()
        self.after(50, self.apply_caption_color)
        self.after(1000, self._tick)

    # ---------- Khung cửa sổ ----------

    def _restore_geometry(self):
        saved = self.store.setting("window")
        if saved:
            size, _, position = saved.partition("+")
            x, _, y = position.partition("+")
            visible = x and MonitorFromPoint(w.POINT(int(x) + 200, int(y) + 40), MONITOR_DEFAULTTONULL)
            self.geometry(saved if visible else size)
        else:
            self.geometry(DEFAULT_SIZE)

    def apply_caption_color(self):
        """Tô thanh tiêu đề cùng màu thanh bên để cửa sổ liền mạch trên Windows 11."""
        hwnd = ctypes.windll.user32.GetAncestor(self.winfo_id(), GA_ROOT)
        color = c_int(colorref(resolve(SIDEBAR)))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(w.HWND(hwnd), DWMWA_CAPTION_COLOR, byref(color), sizeof(color))

    def _on_close(self):
        editor = self._open_editor()
        if editor:
            editor.flush()
        scale = ScalingTracker.get_window_scaling(self)
        width, height = round(self.winfo_width() / scale), round(self.winfo_height() / scale)
        if self.state() == "normal":
            self.store.set_setting("window", f"{width}x{height}+{self.winfo_x()}+{self.winfo_y()}")
        self.destroy()

    def _build_sidebar(self):
        side = ctk.CTkFrame(self, fg_color=SIDEBAR, corner_radius=0, width=216)
        side.grid(row=0, column=0, sticky="ns")
        side.pack_propagate(False)
        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.pack(fill="x", padx=16, pady=(16, 14))
        ctk.CTkLabel(brand, text=Icon.CHECK, width=30, height=30, corner_radius=9, fg_color=FILL, text_color=ON_FILL,
                     font=theme.icon(15)).pack(side="left")
        ctk.CTkLabel(brand, text=APP_NAME, font=theme.display(17), text_color=TEXT).pack(side="left", padx=(10, 0))

        self.nav = {}
        items = (("dashboard", Icon.HOME, "Tổng quan"), ("calendar", Icon.CALENDAR, "Lịch"), ("almanac", Icon.MOON, "Vạn niên"),
                 ("today", Icon.TODAY, "Hôm nay"), ("upcoming", Icon.UPCOMING, "Sắp tới"), ("all", Icon.LIST, "Tất cả"),
                 ("done", Icon.DONE, "Đã xong"))
        for key, glyph, label in items:
            item = NavItem(side, glyph, label, lambda k=key: self.navigate(k))
            item.pack(fill="x", padx=10, pady=1)
            self.nav[key] = item

        ctk.CTkLabel(side, text="Tag", font=theme.text(12), text_color=MUTED, anchor="w", height=20).pack(fill="x", padx=20, pady=(14, 2))
        self.settings_item = NavItem(side, Icon.SETTINGS, "Cài đặt", lambda: self.navigate("settings"))
        self.settings_item.pack(side="bottom", fill="x", padx=10, pady=(0, 12))
        self.nav["settings"] = self.settings_item
        self.tags_frame = ctk.CTkScrollableFrame(side, fg_color="transparent", scrollbar_button_color=SIDEBAR,
                                                 scrollbar_button_hover_color=MUTED)
        self.tags_frame.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 6))

    def _load_tag_colors(self):
        rows = self.store.tags()
        self.tag_colors = {row["name"]: row["color"] for row in rows}
        return rows

    def tag_color(self, name):
        return self.tag_colors.get(name, theme.TAG_FALLBACK)

    def _render_tags(self):
        rows = self._load_tag_colors()
        signature = [(row["id"], row["name"], row["color"]) for row in rows]
        if signature != self.tag_signature:
            self.tag_signature = signature
            for child in self.tags_frame.winfo_children():
                child.destroy()
            self.tag_items = {}
            for row in rows:
                tag_id, name = row["id"], row["name"]
                item = NavItem(self.tags_frame, Icon.DOT, name, lambda i=tag_id: self.navigate(f"tag:{i}"), height=32,
                               glyph_color=tag_edge(row["color"]), glyph_size=10)
                item.pack(fill="x", padx=(10, 0), pady=1)
                self.tag_items[tag_id] = item
            self._mark_active()
        for row in rows:
            self.tag_items[row["id"]].set_count(row["n"])

    # ---------- Điều hướng ----------

    def _page(self, name):
        """Trang chỉ được dựng khi mở lần đầu, giúp cửa sổ hiện nhanh hơn."""
        if name not in self.pages:
            factory = {"dashboard": Dashboard, "calendar": CalendarPage, "almanac": almanac_page, "tasks": TasksPage,
                       "settings": SettingsPage}[name]
            self.pages[name] = factory(self.content, self)
            self.pages[name].grid(row=0, column=0, sticky="nsew")
        return self.pages[name]

    def navigate(self, key):
        editor = self._open_editor()
        if editor:
            editor.flush()
        if key in ("dashboard", "calendar", "almanac", "settings"):
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
        self._mark_active()
        self.refresh()
        self.snackbar.lift()

    def _mark_active(self):
        for key, item in self.nav.items():
            item.set_active(key == self.current_key)
        for tag_id, item in self.tag_items.items():
            item.set_active(self.current_key == f"tag:{tag_id}")

    def open_task(self, task_id):
        task = self.store.get_task(task_id)
        if task is None:
            return
        view = "done" if task["done_at"] else "all"
        self.navigate(view)
        self.pages["tasks"].open_editor(task_id)

    def _open_editor(self):
        page = self.current_page
        return page.editor if getattr(page, "editor_open", False) else None

    def close_editor(self):
        if hasattr(self.current_page, "close_editor"):
            self.current_page.close_editor()

    def _focus_quick(self):
        if self.current_key == "settings":
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
        stats = self.store.stats(now)
        self.nav["today"].set_count(stats["today_open"] + stats["overdue"])
        self.nav["upcoming"].set_count(stats["upcoming"])
        self.nav["all"].set_count(stats["open_total"])
        self._render_tags()
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

    def _tick(self):
        """Chỉ cập nhật đồng hồ đếm ngược; dữ liệu do tiến trình khác đổi được phát hiện qua data_version."""
        now = datetime.now()
        try:
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
            elif self.current_page is self.pages.get("dashboard"):
                self.current_page.tick(now)
        finally:
            self.after(1000, self._tick)


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
    # CustomTkinter mặc định dò theme 33 lần/giây và dò DPI 10 lần/giây: hạ xuống 1 lần/giây.
    AppearanceModeTracker.update_loop_interval = 1000
    ScalingTracker.update_loop_interval = 1000
    store = Store()
    ctk.set_appearance_mode(store.setting("theme"))
    store.close()
    App().mainloop()
