"""Ba trang của ứng dụng: Tổng quan, danh sách task, cài đặt."""
import os
import threading
from datetime import datetime, timedelta
from queue import SimpleQueue

import customtkinter as ctk
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from .. import APP_NAME, __version__, integration
from ..db import DEFAULT_SETTINGS, TAG_COLORS
from ..lunar import lunar_text, solar_to_lunar
from ..paths import DATA_DIR
from ..schedule import REMIND_CHOICES, WEEKDAY_LONG, active_block, block_window, countdown, from_text, humanize, next_block, parse_offsets
from ..win32 import WM_APP_SUMMARY, post_agent
from . import theme
from .editor import BLOCK_PRESETS, REMIND_LABELS, TaskEditor
from .theme import (ACCENT, ACCENT_SOFT, AMBER, BG, BORDER, CARD_HOVER, FILL, GREEN, GREEN_SOFT, Icon, MUTED, RED, RED_SOFT, TEXT, TRACK)
from .widgets import Card, Chip, IconButton, QuickEntry, TaskList, WeekChart, field, group_entries, primary_button, secondary_button, segmented, set_text

VIEW_TITLES = {"today": "Hôm nay", "upcoming": "Sắp tới", "all": "Tất cả việc", "done": "Đã xong"}
EMPTY_TEXTS = {"today": "Hôm nay chưa có việc nào.\nGõ vào ô phía trên để thêm việc đầu tiên.",
               "upcoming": "Chưa có việc nào sắp tới.", "all": "Danh sách trống. Thêm việc đầu tiên nhé!",
               "done": "Chưa hoàn thành việc nào."}
GREETING_HOURS = ((5, "Khuya rồi"), (11, "Chào buổi sáng"), (13, "Chào buổi trưa"), (18, "Chào buổi chiều"), (22, "Chào buổi tối"))
MAX_BLOCK_LINES = 5
LONG_FIELD_WIDTH = 300
SAVED_HINT = "Đã lưu, nhập để thay"


def greeting(hour):
    for limit, phrase in GREETING_HOURS:
        if hour < limit:
            return phrase
    return "Khuya rồi"


def bind_click(root, command):
    """Cả thẻ bấm được: gắn sự kiện cho thẻ và mọi widget bên trong."""
    root.bind("<Button-1>", lambda _: command())
    for child in root.winfo_children():
        bind_click(child, command)


class KpiCard(Card):
    def __init__(self, master, title, glyph, color, tint):
        super().__init__(master, height=124)
        self.pack_propagate(False)
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(self.header, text=title, font=theme.text(13), text_color=MUTED, height=30).pack(side="left")
        ctk.CTkLabel(self.header, text=glyph, width=30, height=30, corner_radius=8, fg_color=tint, text_color=color,
                     font=theme.icon(15)).pack(side="right")
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=16, pady=(0, 10))


class NumberCard(KpiCard):
    def __init__(self, master, title, glyph, color, tint):
        super().__init__(master, title, glyph, color, tint)
        self.number = ctk.CTkLabel(self.body, text="0", font=theme.display(36), text_color=TEXT, anchor="w", height=42)
        self.number.pack(fill="x")
        self.note = ctk.CTkLabel(self.body, text="", font=theme.text(12), text_color=MUTED, anchor="w", height=18)
        self.note.pack(fill="x")

    def show(self, number, note, color=TEXT):
        self.number.configure(text=str(number), text_color=color)
        self.note.configure(text=note)


class RateCard(KpiCard):
    def __init__(self, master):
        super().__init__(master, "Tỷ lệ hoàn thành", Icon.DONE, GREEN, GREEN_SOFT)
        self.number = ctk.CTkLabel(self.body, text="—", font=theme.display(36), text_color=TEXT, anchor="w", height=36)
        self.number.pack(fill="x")
        self.bar = ctk.CTkProgressBar(self.body, height=6, corner_radius=3, fg_color=TRACK, progress_color=GREEN)
        self.bar.pack(fill="x", pady=(0, 2))
        self.note = ctk.CTkLabel(self.body, text="", font=theme.text(12), text_color=MUTED, anchor="w", height=18)
        self.note.pack(fill="x")

    def show(self, stats):
        rate = stats["rate"]
        self.number.configure(text="—" if rate is None else f"{round(rate * 100)}%")
        self.bar.set(rate or 0)
        self.note.configure(text=f"{stats['done_today']}/{stats['planned']} việc hôm nay")


class WeekCard(KpiCard):
    def __init__(self, master):
        super().__init__(master, "7 ngày qua", Icon.CHART, ACCENT, ACCENT_SOFT)
        self.total = ctk.CTkLabel(self.header, text="", font=theme.semibold(13), text_color=TEXT, height=30)
        self.total.pack(side="right", padx=(0, 8))
        self.chart = WeekChart(self.body)
        self.chart.pack(fill="both", expand=True, pady=(4, 0))

    def show(self, week):
        self.total.configure(text=f"{sum(count for _, count in week)} việc")
        self.chart.set_week(week)


class FocusCard(Card):
    """Thẻ đếm ngược time-blocking."""

    def __init__(self, master, app, dashboard):
        super().__init__(master)
        self.app = app
        self.dashboard = dashboard
        self.current_id = None
        self.block = None
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(header, text="Tập trung", font=theme.semibold(15), text_color=TEXT, height=24).pack(side="left")
        ctk.CTkLabel(header, text=Icon.TIMER, font=theme.icon(15), text_color=ACCENT, height=24).pack(side="right")
        self._build_active()
        self._build_idle()
        self.active.pack(fill="x", padx=16, pady=(4, 14))

    def _build_active(self):
        self.active = ctk.CTkFrame(self, fg_color="transparent")
        self.active_title = ctk.CTkLabel(self.active, text="", font=theme.text(13), text_color=MUTED, anchor="w", height=20)
        self.active_title.pack(fill="x")
        self.clock = ctk.CTkLabel(self.active, text="00:00", font=theme.display(50), text_color=ACCENT, anchor="w", height=64)
        self.clock.pack(fill="x")
        self.progress = ctk.CTkProgressBar(self.active, height=6, corner_radius=3, fg_color=TRACK, progress_color=ACCENT)
        self.progress.pack(fill="x", pady=(2, 10))
        buttons = ctk.CTkFrame(self.active, fg_color="transparent")
        buttons.pack(fill="x")
        secondary_button(buttons, "+5 phút", self._extend, width=78).pack(side="left")
        secondary_button(buttons, "Kết thúc", self._finish, width=78).pack(side="left", padx=(6, 0))
        primary_button(buttons, "Hoàn thành", self._complete).pack(side="left", fill="x", expand=True, padx=(6, 0))

    def _build_idle(self):
        self.idle = ctk.CTkFrame(self, fg_color="transparent")
        self.idle_text = ctk.CTkLabel(self.idle, text="", font=theme.text(13), text_color=MUTED, anchor="w", justify="left")
        self.idle_text.pack(fill="x")
        self.idle.bind("<Configure>", self._wrap_idle_text)
        self.presets = ctk.CTkFrame(self.idle, fg_color="transparent")
        self.presets.pack(fill="x", pady=(8, 0))
        for minutes in BLOCK_PRESETS:
            secondary_button(self.presets, f"{minutes} phút", lambda m=minutes: self._start(m), width=60).pack(
                side="left", fill="x", expand=True, padx=(0, 6 if minutes != BLOCK_PRESETS[-1] else 0))

    def _wrap_idle_text(self, event):
        self.idle_text.configure(wraplength=event.width / ScalingTracker.get_widget_scaling(self))

    def _start(self, minutes):
        task_id = self.dashboard.selected_id
        if task_id:
            self.app.store.start_block(task_id, minutes)
            self.app.changed()

    def _extend(self):
        self.app.store.extend_block(self.current_id, 5)
        self.app.changed()

    def _finish(self):
        self.app.store.end_block(self.current_id)
        self.app.changed()

    def _complete(self):
        task = self.app.store.get_task(self.current_id)
        self.app.store.end_block(self.current_id)
        self.app.toggle_task(task)

    def refresh(self, tasks, now):
        block = active_block(tasks, now)
        self.current_id = block[0]["id"] if block else None
        if block:
            self.idle.pack_forget()
            self.active.pack(fill="x", padx=16, pady=(4, 14))
            title = block[0]["title"]
            self.active_title.configure(text=title if len(title) <= 42 else title[:41] + "…")
            self.block = block
            self.tick(now)
            return
        self.block = None
        self.active.pack_forget()
        self.idle.pack(fill="x", padx=16, pady=(4, 14))
        selected = self.app.store.get_task(self.dashboard.selected_id) if self.dashboard.selected_id else None
        coming = next_block(tasks, now)
        lines = []
        if selected and not selected["done_at"]:
            lines.append(f"Bắt đầu đếm ngược cho: {selected['title']}")
        else:
            lines.append("Chọn một việc trong danh sách, rồi chọn thời lượng để bắt đầu đếm ngược.")
        if coming:
            lines.append(f"Khối tiếp theo {coming[1]:%H:%M}: {coming[0]['title']} (sau {humanize(coming[1] - now)})")
        self.idle_text.configure(text="\n".join(lines))

    def tick(self, now):
        if not self.block:
            return
        task, start, end = self.block
        if now >= end:
            self.dashboard.app.refresh()
            return
        self.clock.configure(text=countdown(end - now))
        self.progress.set(min(max((end - now) / (end - start), 0), 1))


class Dashboard(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=BG)
        self.app = app
        self.store = app.store
        self.selected_id = None
        self.deadline = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 10))
        self.hello = ctk.CTkLabel(header, text="", font=theme.display(26), text_color=TEXT, anchor="w", height=34)
        self.hello.pack(fill="x")
        self.today_label = ctk.CTkLabel(header, text="", font=theme.text(13), text_color=MUTED, anchor="w", height=20)
        self.today_label.pack(fill="x")

        self.quick = QuickEntry(self, app)
        self.quick.grid(row=1, column=0, sticky="ew", padx=24)

        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.grid(row=2, column=0, sticky="ew", padx=24, pady=(8, 12))
        cards.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="kpi")
        self.today_card = NumberCard(cards, "Hôm nay", Icon.TODAY, ACCENT, ACCENT_SOFT)
        self.overdue_card = NumberCard(cards, "Quá hạn", Icon.WARNING, RED, RED_SOFT)
        self.rate_card = RateCard(cards)
        self.week_card = WeekCard(cards)
        targets = ((self.today_card, "today"), (self.overdue_card, "today"), (self.rate_card, "done"), (self.week_card, "calendar"))
        for column, (card, target) in enumerate(targets):
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0 if column == 3 else 6))
            bind_click(card, lambda key=target: app.navigate(key))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 20))
        body.grid_columnconfigure(0, weight=3, uniform="body")
        body.grid_columnconfigure(1, weight=2, uniform="body")
        body.grid_rowconfigure(0, weight=1)

        tasks_card = Card(body)
        tasks_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ctk.CTkLabel(tasks_card, text="Việc cần làm hôm nay", font=theme.semibold(15), text_color=TEXT, anchor="w", height=24).pack(
            fill="x", padx=16, pady=(12, 4))
        self.task_list = TaskList(tasks_card, app, self._select, app.open_task, EMPTY_TEXTS["today"])
        self.task_list.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        side = ctk.CTkFrame(body, fg_color="transparent")
        side.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.focus_card = FocusCard(side, app, self)
        self.focus_card.pack(fill="x")
        agenda = Card(side)
        agenda.pack(fill="both", expand=True, pady=(12, 0))
        ctk.CTkLabel(agenda, text="Mốc tiếp theo", font=theme.semibold(15), text_color=TEXT, anchor="w", height=24).pack(
            fill="x", padx=16, pady=(12, 2))
        self.deadline_title = ctk.CTkLabel(agenda, text="", font=theme.text(13), text_color=MUTED, anchor="w", height=20)
        self.deadline_title.pack(fill="x", padx=16)
        self.deadline_clock = ctk.CTkLabel(agenda, text="", font=theme.display(24), text_color=TEXT, anchor="w", height=34)
        self.deadline_clock.pack(fill="x", padx=16)
        ctk.CTkLabel(agenda, text="Khối giờ hôm nay", font=theme.text(12), text_color=MUTED, anchor="w", height=20).pack(
            fill="x", padx=16, pady=(6, 0))
        self.blocks = ctk.CTkLabel(agenda, text="", font=theme.text(13), text_color=TEXT, anchor="nw", justify="left")
        self.blocks.pack(fill="both", expand=True, padx=16, pady=(0, 10))

    def _select(self, task_id):
        self.selected_id = task_id
        self.focus_card.refresh(self.store.scheduled_tasks(), datetime.now())

    def refresh(self, now):
        stats = self.store.stats(now)
        self.hello.configure(text=greeting(now.hour))
        self.today_label.configure(text=f"{WEEKDAY_LONG[now.weekday()]}, {now:%d/%m/%Y} · {lunar_text(solar_to_lunar(now.date()))} âm lịch")
        self.today_card.show(stats["today_open"], f"còn lại · {stats['done_today']} đã xong")
        overdue = stats["overdue"]
        self.overdue_card.show(overdue, "cần xử lý ngay" if overdue else "Không có việc trễ", RED if overdue else GREEN)
        self.rate_card.show(stats)
        self.week_card.show(stats["week"])
        self.task_list.set_entries(group_entries(self.store.list_tasks("today", now), now, "today"))
        self.task_list.select(self.selected_id)
        self.focus_card.refresh(self.store.scheduled_tasks(), now)
        self.deadline = self.store.nearest_deadline(now)
        if self.deadline:
            title = self.deadline["title"]
            self.deadline_title.configure(text=title if len(title) <= 40 else title[:39] + "…")
        else:
            self.deadline_title.configure(text="Không có hạn nào sắp tới")
            self.deadline_clock.configure(text="")
        rows = self.store.blocks_today(now)
        lines = []
        for row in rows[:MAX_BLOCK_LINES]:
            start, end = block_window(row)
            lines.append(f"{start:%H:%M}–{end:%H:%M}   {row['title'][:30]}")
        if len(rows) > MAX_BLOCK_LINES:
            lines.append(f"+{len(rows) - MAX_BLOCK_LINES} khối khác")
        self.blocks.configure(text="\n".join(lines) or "Chưa đặt khối giờ nào", text_color=TEXT if lines else MUTED)
        self.tick(now)

    def tick(self, now):
        self.focus_card.tick(now)
        if self.deadline:
            left = from_text(self.deadline["due_at"]) - now
            if left.total_seconds() <= 0:
                self.app.refresh()
                return
            text = f"{left.days} ngày {countdown(left - timedelta(days=left.days))}" if left.days else countdown(left)
            self.deadline_clock.configure(text=text, text_color=AMBER if left < timedelta(hours=1) else TEXT)


class TasksPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=BG)
        self.app = app
        self.store = app.store
        self.view = "today"
        self.tag_id = 0
        self.tag_name = ""
        self.search_text = ""
        self.editor = None  # panel khá nặng nên chỉ dựng khi mở lần đầu
        self.editor_open = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=(24, 12), pady=(18, 8))
        self.title_label = ctk.CTkLabel(header, text="", font=theme.display(25), text_color=TEXT, anchor="w", height=34)
        self.title_label.pack(side="left")
        self.count_label = ctk.CTkLabel(header, text="", font=theme.text(14), text_color=MUTED, height=34)
        self.count_label.pack(side="left", padx=(10, 0), pady=(4, 0))
        self.search = field(header, width=170, placeholder_text="Tìm kiếm…   (Ctrl+F)")
        self.search.pack(side="right")
        self.search.bind("<KeyRelease>", self._on_search)

        self.quick = QuickEntry(self, app)
        self.quick.grid(row=1, column=0, sticky="ew", padx=(24, 12))

        card = Card(self)
        card.grid(row=2, column=0, sticky="nsew", padx=(24, 12), pady=(8, 20))
        self.task_list = TaskList(card, app, self._select)
        self.task_list.pack(fill="both", expand=True, padx=8, pady=8)

    def show_view(self, view, tag_id=0, tag_name=""):
        self.view, self.tag_id, self.tag_name = view, tag_id, tag_name
        set_text(self.search, "")
        self.search_text = ""
        self.refresh(datetime.now())

    def refresh(self, now):
        self.title_label.configure(text=self.tag_name or VIEW_TITLES[self.view])
        tasks = self.store.list_tasks(self.view, now, self.tag_id, self.search_text)
        self.count_label.configure(text=str(len(tasks)) if tasks else "")
        self.task_list.empty_text = "Không tìm thấy việc nào." if self.search_text else EMPTY_TEXTS[self.view]
        self.task_list.set_entries(group_entries(tasks, now, self.view))

    def _on_search(self, _event=None):
        value = self.search.get().strip()
        if value != self.search_text:
            self.search_text = value
            self.refresh(datetime.now())

    def _select(self, task_id):
        self.open_editor(task_id)

    def open_editor(self, task_id):
        if self.editor is None:
            self.editor = TaskEditor(self, self.app)
        if not self.editor_open:
            self.editor.grid(row=0, column=1, rowspan=3, sticky="ns", padx=(0, 24), pady=(18, 20))
            self.editor_open = True
        self.task_list.select(task_id)
        self.editor.load(task_id)

    def close_editor(self):
        if self.editor_open:
            self.editor.grid_remove()
            self.editor_open = False
            self.editor.task_id = None
            self.editor.task = None
        self.task_list.select(None)


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=BG)
        self.app = app
        self.store = app.store
        self.brief_status_shown = None
        ctk.CTkLabel(self, text="Cài đặt", font=theme.display(25), text_color=TEXT, anchor="w", height=34).pack(
            fill="x", padx=24, pady=(18, 10))
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=TRACK,
                                        scrollbar_button_hover_color=MUTED)
        scroll.pack(fill="both", expand=True, padx=(16, 8), pady=(0, 16))
        self.scroll = scroll

        section = self._section("Giao diện")
        row = self._row(section, "Chủ đề màu", "Tối là nền đen, nhấn xanh dương, độ tương phản cao")
        labels = {"Tối": "dark", "Sáng": "light", "Hệ thống": "system"}
        self.theme_choice = segmented(row, list(labels), lambda label: self._set_theme(labels[label]))
        self.theme_choice.pack(side="right")
        self.theme_choice.set(next(k for k, v in labels.items() if v == self.store.setting("theme")))

        section = self._section("Tag")
        self.tag_rows = ctk.CTkFrame(section, fg_color="transparent")
        self.tag_rows.pack(fill="x", padx=16, pady=(10, 0))
        self.new_tag = field(section, placeholder_text="+ Tạo tag mới, Enter để lưu")
        self.new_tag.pack(fill="x", padx=16, pady=(4, 12))
        self.new_tag.bind("<Return>", self._add_tag)
        self._render_tags()

        section = self._section("Khởi động và nền")
        row = self._row(section, "Khởi động cùng Windows", "Chạy ngầm và gửi tóm tắt ngay khi đăng nhập")
        self.autostart = self._switch(row, integration.autostart_enabled(), self._set_autostart)
        row = self._row(section, "Phím tắt Thêm nhanh", "Ctrl+Alt+T ở bất kỳ đâu trong Windows")
        self._switch(row, self.store.setting("hotkey") == "1", lambda on: self._set_flag("hotkey", on))
        row = self._row(section, "Đồng hồ đếm ngược nổi", "Hiện góc màn hình khi khối thời gian đang chạy")
        self._switch(row, self.store.setting("timer_pill") == "1", lambda on: self._set_flag("timer_pill", on))

        section = self._section("Thông báo")
        row = self._row(section, "Giờ gửi tóm tắt mỗi sáng", "Dành cho PC bật xuyên đêm, định dạng HH:MM")
        self.summary_time = field(row, width=76, justify="center")
        set_text(self.summary_time, self.store.setting("summary_time"))
        self.summary_time.pack(side="right")
        self.summary_time.bind("<FocusOut>", lambda _: self._save_time(self.summary_time, "summary_time"))
        self.summary_time.bind("<Return>", lambda _: self._save_time(self.summary_time, "summary_time"))
        row = self._row(section, "Nhắc trước hạn mặc định", "Áp dụng cho việc tạo mới")
        self.remind_chips = {}
        chosen = parse_offsets(self.store.setting("default_remind"))
        for minutes in reversed(REMIND_CHOICES):
            chip = Chip(row, REMIND_LABELS[minutes], lambda m=minutes: self._toggle_remind(m), width=48)
            chip.set_active(minutes in chosen)
            chip.pack(side="right", padx=(6, 0))
            self.remind_chips[minutes] = chip
        row = self._row(section, "Gửi tóm tắt ngay", "Dùng để kiểm tra thông báo Windows có bị chặn không")
        secondary_button(row, "Gửi thử", lambda: post_agent(WM_APP_SUMMARY), width=84).pack(side="right")

        self._build_telegram()
        self._build_ai()

        section = self._section("Dữ liệu")
        row = self._row(section, "Thư mục dữ liệu", DATA_DIR if len(DATA_DIR) <= 72 else "…" + DATA_DIR[-71:])
        secondary_button(row, "Mở thư mục", lambda: os.startfile(DATA_DIR), width=104).pack(side="right")
        ctk.CTkLabel(scroll, text=f"{APP_NAME} {__version__}", font=theme.text(12), text_color=MUTED, anchor="w").pack(
            fill="x", padx=8, pady=(10, 0))

    def _build_telegram(self):
        store = self.store
        section = self._section("Bot Telegram")
        row = self._row(section, "Bản tin mỗi ngày", "Thần tâu lên hoàng thượng qua Telegram, mỗi ngày một lần")
        self._switch(row, store.setting("telegram_enabled") == "1", self._set_brief_enabled)
        row = self._row(section, "Bot Token", "Nhắn @BotFather để tạo bot. Token được mã hoá trên máy này")
        self._secret_field(row, "telegram_token", "123456:ABC-DEF…")
        row = self._row(section, "Chat ID", "Nhắn /start cho bot rồi bấm Lấy tự động")
        self.chat_button = secondary_button(row, "Lấy tự động", self._fetch_chat, width=96)
        self.chat_button.pack(side="right", padx=(8, 0))
        self.chat_id = field(row, width=LONG_FIELD_WIDTH - 104, justify="center")
        set_text(self.chat_id, store.setting("telegram_chat_id"))
        self.chat_id.pack(side="right")
        self.chat_id.bind("<FocusOut>", self._save_chat_id)
        self.chat_id.bind("<Return>", self._save_chat_id)
        row = self._row(section, "API URL", "Chỉ đổi khi dùng máy chủ riêng hoặc proxy")
        self._url_field(row, "telegram_api_url")
        row = self._row(section, "Giờ gửi", "Dành cho PC bật xuyên đêm, định dạng HH:MM")
        self.brief_time = field(row, width=76, justify="center")
        set_text(self.brief_time, store.setting("telegram_time"))
        self.brief_time.pack(side="right")
        self.brief_time.bind("<FocusOut>", lambda _: self._save_time(self.brief_time, "telegram_time"))
        self.brief_time.bind("<Return>", lambda _: self._save_time(self.brief_time, "telegram_time"))
        row = self._row(section, "Gửi khi PC bật lần đầu trong ngày", "Tắt đi thì chỉ gửi đúng giờ đã đặt")
        self._switch(row, store.setting("telegram_on_start") == "1", lambda on: self._set_flag("telegram_on_start", on))
        row = self._row(section, "Kiểm tra", "Gửi thử sẽ gửi đúng bản tin của hôm nay")
        self.send_button = secondary_button(row, "Gửi thử", self._send_test, width=84)
        self.send_button.pack(side="right")
        self.check_button = secondary_button(row, "Kiểm tra bot", self._check_bot, width=104)
        self.check_button.pack(side="right", padx=(0, 6))
        self.brief_status = ctk.CTkLabel(section, text="", font=theme.text(12), text_color=MUTED, anchor="w", justify="left", wraplength=620)
        self.brief_status.pack(fill="x", padx=16, pady=(0, 10))
        self.refresh(None)

    def _build_ai(self):
        section = self._section("AI cho trang Tử vi")
        row = self._row(section, "API key", "Không bắt buộc: chưa có key thì Tử vi luận mẫu ngay trên máy")
        self._secret_field(row, "ai_key", "sk-…")
        row = self._row(section, "API URL", "Dịch vụ bất kỳ theo chuẩn OpenAI, mặc định là DeepSeek")
        self._url_field(row, "ai_url")
        row = self._row(section, "Model", "Tên model của dịch vụ đang dùng")
        self.ai_model = field(row, width=LONG_FIELD_WIDTH)
        set_text(self.ai_model, self.store.setting("ai_model"))
        self.ai_model.pack(side="right")
        self.ai_model.bind("<FocusOut>", self._save_ai_model)
        self.ai_model.bind("<Return>", self._save_ai_model)

    def _section(self, title):
        ctk.CTkLabel(self.scroll, text=title, font=theme.semibold(15), text_color=TEXT, anchor="w", height=24).pack(
            fill="x", padx=8, pady=(10, 4))
        card = Card(self.scroll)
        card.pack(fill="x", padx=(8, 8), pady=(0, 6))
        return card

    def _row(self, card, title, note):
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=8)
        labels = ctk.CTkFrame(row, fg_color="transparent")
        labels.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(labels, text=title, font=theme.text(14), text_color=TEXT, anchor="w", height=20).pack(fill="x")
        ctk.CTkLabel(labels, text=note, font=theme.text(12), text_color=MUTED, anchor="w", height=18).pack(fill="x")
        return row

    def _switch(self, row, value, command):
        switch = ctk.CTkSwitch(row, text="", width=44, progress_color=FILL, fg_color=TRACK,
                               command=lambda: command(switch.get() == 1))
        if value:
            switch.select()
        switch.pack(side="right")
        return switch

    # ---------- Tag ----------

    def _render_tags(self):
        for child in self.tag_rows.winfo_children():
            child.destroy()
        for tag in self.store.tags():
            self._tag_row(tag)

    def _tag_row(self, tag):
        row = ctk.CTkFrame(self.tag_rows, fg_color="transparent")
        row.pack(fill="x", pady=(0, 6))
        tag_id, color = tag["id"], tag["color"]
        ctk.CTkButton(row, text="", width=24, height=24, corner_radius=12, fg_color=color, hover_color=color,
                      command=lambda: self._next_color(tag_id, color)).pack(side="left", padx=(0, 10))
        name = field(row, height=30)
        set_text(name, tag["name"])
        name.pack(side="left", fill="x", expand=True)
        name.bind("<Return>", lambda _: self._rename_tag(tag_id, name))
        name.bind("<FocusOut>", lambda _: self._rename_tag(tag_id, name))
        ctk.CTkLabel(row, text=f"{tag['n']} việc" if tag["n"] else "", width=56, font=theme.text(12), text_color=MUTED).pack(side="left", padx=(8, 0))
        IconButton(row, Icon.DELETE, lambda: self._delete_tag(tag_id, tag["name"]), size=30).pack(side="left")

    def _next_color(self, tag_id, color):
        position = TAG_COLORS.index(color) if color in TAG_COLORS else -1
        self.store.set_tag_color(tag_id, TAG_COLORS[(position + 1) % len(TAG_COLORS)])
        self.app.changed()
        self._render_tags()

    def _rename_tag(self, tag_id, entry):
        value = entry.get().strip()
        current = next((row["name"] for row in self.store.tags() if row["id"] == tag_id), None)
        if current is None or value == current:
            return
        if self.store.rename_tag(tag_id, value):
            self.app.changed()
        else:
            set_text(entry, current)
            self.app.snackbar.show("Tên tag trống hoặc đã có")

    def _delete_tag(self, tag_id, name):
        self.store.delete_tag(tag_id)
        self.app.changed()
        self._render_tags()
        self.app.snackbar.show(f"Đã xoá tag {name}, các việc vẫn được giữ nguyên")

    def _add_tag(self, _event=None):
        name = self.new_tag.get().strip()
        if name:
            self.store.ensure_tag(name)
            set_text(self.new_tag, "")
            self.app.changed()
            self._render_tags()
        return "break"

    # ---------- Tuỳ chọn khác ----------

    def _set_theme(self, value):
        self.store.set_setting("theme", value)
        ctk.set_appearance_mode(value)
        self.app.apply_caption_color()

    def _set_autostart(self, enabled):
        integration.set_autostart(enabled)

    def _set_flag(self, key, enabled):
        self.store.set_setting(key, "1" if enabled else "0")
        self.app.changed()

    def _save_time(self, entry, key):
        value = entry.get().strip()
        parts = value.split(":")
        valid = len(parts) == 2 and all(p.isdigit() for p in parts) and int(parts[0]) < 24 and int(parts[1]) < 60
        entry.configure(border_color=BORDER if valid else RED)
        if valid:
            normalized = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
            set_text(entry, normalized)
            if normalized != self.store.setting(key):
                self.store.set_setting(key, normalized)
                self.app.changed()

    def _toggle_remind(self, minutes):
        chip = self.remind_chips[minutes]
        chip.set_active(not chip.active)
        chosen = [str(value) for value in REMIND_CHOICES if self.remind_chips[value].active]
        self.store.set_setting("default_remind", ",".join(reversed(chosen)))

    # ---------- Bot Telegram và AI ----------

    def refresh(self, _now):
        status = self.store.setting("telegram_status")
        if status != self.brief_status_shown:
            self.brief_status_shown = status
            self._show_brief_status(status or "Chưa gửi bản tin nào")

    def _show_brief_status(self, text, color=MUTED):
        self.brief_status.configure(text=text, text_color=color)

    def _secret_field(self, row, key, hint):
        """Ô nhập khoá bí mật: đã lưu thì không bao giờ hiện lại, chỉ có thể nhập đè hoặc xoá."""
        entry = field(row, width=LONG_FIELD_WIDTH - 36, show="•", placeholder_text=SAVED_HINT if self.store.setting(key) else hint)

        def save(_event=None):
            value = entry.get().strip()
            if value:
                self._set_secret(key, value)
                entry.configure(placeholder_text=SAVED_HINT)
                set_text(entry, "")

        def forget():
            self._set_secret(key, "")
            entry.configure(placeholder_text=hint)
            set_text(entry, "")

        IconButton(row, Icon.DELETE, forget, size=30).pack(side="right", padx=(6, 0))
        entry.pack(side="right")
        entry.bind("<FocusOut>", save)
        entry.bind("<Return>", save)

    def _url_field(self, row, key):
        entry = field(row, width=LONG_FIELD_WIDTH)
        set_text(entry, self.store.setting(key))
        entry.pack(side="right")
        entry.bind("<FocusOut>", lambda _: self._save_url(entry, key))
        entry.bind("<Return>", lambda _: self._save_url(entry, key))

    def _save_url(self, entry, key):
        from ..web import ApiError, check_api_url
        try:
            value = check_api_url(entry.get() or DEFAULT_SETTINGS[key])
        except ApiError:
            entry.configure(border_color=RED)
            return
        entry.configure(border_color=BORDER)
        set_text(entry, value)
        if value != self.store.setting(key):
            self.store.set_setting(key, value)
            if key == "telegram_api_url":
                self._brief_setup_changed(self._brief_ready())

    def _save_ai_model(self, _event=None):
        value = self.ai_model.get().strip() or DEFAULT_SETTINGS["ai_model"]
        set_text(self.ai_model, value)
        self.store.set_setting("ai_model", value)

    def _set_secret(self, key, value):
        ready = self._brief_ready()
        self.store.set_secret(key, value)
        if key == "telegram_token":
            self._brief_setup_changed(ready)

    def _brief_ready(self):
        return self.store.setting("telegram_enabled") == "1" and all(self.store.setting(key) for key in ("telegram_token", "telegram_chat_id"))

    def _brief_setup_changed(self, was_ready):
        """Vừa cài xong mà đã quá giờ thì chưa bắn tin ngay: bản tin đầu đi vào ngày mai, muốn xem liền thì bấm Gửi thử."""
        now = datetime.now()
        self.store.set_setting("telegram_failed_on", "")
        if self._brief_ready() and not was_ready and f"{now:%H:%M}" >= self.store.setting("telegram_time"):
            self.store.set_setting("telegram_last_sent", now.date().isoformat())
        self.app.changed()

    def _set_brief_enabled(self, enabled):
        ready = self._brief_ready()
        self.store.set_setting("telegram_enabled", "1" if enabled else "0")
        self._brief_setup_changed(ready)

    def _save_chat_id(self, _event=None):
        value = self.chat_id.get().strip()
        if value != self.store.setting("telegram_chat_id"):
            ready = self._brief_ready()
            self.store.set_setting("telegram_chat_id", value)
            self._brief_setup_changed(ready)

    def _in_background(self, button, work, done):
        """Gọi mạng ở luồng phụ để giao diện không đứng, xong thì trả kết quả về luồng giao diện."""
        from ..web import ApiError
        results = SimpleQueue()

        def run():
            try:
                results.put((work(), None))
            except ApiError as error:
                results.put((None, str(error)))

        def wait():
            if results.empty():
                self.after(100, wait)
                return
            button.configure(state="normal")
            done(*results.get())

        button.configure(state="disabled")
        threading.Thread(target=run, daemon=True).start()
        self.after(100, wait)

    def _bot_maker(self):
        """Hàm tạo Bot để gọi trong luồng phụ: khoá phải đọc từ luồng giao diện, nơi giữ kết nối SQLite."""
        from ..telegram import Bot
        token, url = self.store.secret("telegram_token"), self.store.setting("telegram_api_url")
        return lambda: Bot(token, url)

    def _check_bot(self):
        make_bot = self._bot_maker()
        self._show_brief_status("Đang kiểm tra…")
        self._in_background(self.check_button, lambda: make_bot().me(), self._on_checked)

    def _on_checked(self, name, error):
        self._show_brief_status(f"Bot {name} đã sẵn sàng" if name else error, GREEN if name else RED)

    def _send_test(self):
        from ..telegram import build_brief
        chat = self.store.setting("telegram_chat_id")
        if not chat:
            self._show_brief_status("Chưa có Chat ID", RED)
            return
        make_bot, content = self._bot_maker(), build_brief(self.store, datetime.now())
        self._show_brief_status("Đang gửi…")
        self._in_background(self.send_button, lambda: make_bot().send(chat, content), self._on_sent)

    def _on_sent(self, message, error):
        self._show_brief_status("Đã gửi thử, hãy xem trong Telegram" if message else error, GREEN if message else RED)

    def _fetch_chat(self):
        make_bot = self._bot_maker()
        self._show_brief_status("Đang tìm tin nhắn gửi cho bot…")
        self._in_background(self.chat_button, lambda: make_bot().latest_chat(), self._on_chat)

    def _on_chat(self, chat, error):
        if chat:
            set_text(self.chat_id, chat[0])
            self._save_chat_id()
            self._show_brief_status(f"Đã lấy Chat ID của {chat[1] or chat[0]}", GREEN)
        else:
            self._show_brief_status(error or "Chưa thấy tin nhắn nào. Hãy nhắn /start cho bot rồi bấm lại", RED)
