"""Ba trang của ứng dụng: Tổng quan, danh sách task, cài đặt."""
import os
import threading
import time
from datetime import datetime, timedelta
from queue import SimpleQueue

import tkinter as tk

import customtkinter as ctk
from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import AppearanceModeTracker
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from .. import APP_NAME, __version__, daybook, integration, quotes
from ..db import DEFAULT_SETTINGS, TAG_COLORS
from ..lunar import lunar_text, solar_to_lunar
from ..paths import DATA_DIR
from ..schedule import REMIND_CHOICES, TELEGRAM_CHOICES, WEEKDAY_LONG, active_block, countdown, from_text, humanize, next_block, parse_offsets
from ..win32 import WM_APP_SUMMARY, post_agent
from . import motion, theme
from .editor import BLOCK_PRESETS, REMIND_LABELS, TaskEditor
from .theme import ACCENT, AMBER, BG, BORDER, CARD, CARD_HOVER, FILL, GREEN, Icon, MUTED, RED, TEXT, TRACK, resolve
from .shapes import rounded
from .textfit import fit_text, side_by_side, uniform_columns
from .widgets import (Card, Chip, DayBand, FitLabel, FontCache, IconButton, Label, Plain, QuickEntry, Scaled, TaskList, scaled, draw_week, field,
                      group_entries, measure_text, primary_button, secondary_button, segmented, set_label, set_text)

SETTING_TABS = ("Chung", "Thông báo", "Telegram", "Tử vi AI")
VIEW_TITLES = {"today": "Hôm nay", "upcoming": "Sắp tới", "all": "Tất cả việc", "done": "Đã xong"}
EMPTY_TEXTS = {"today": "Hôm nay chưa có việc nào.\nGõ vào ô phía trên để thêm việc đầu tiên.",
               "upcoming": "Chưa có việc nào sắp tới.", "all": "Danh sách trống. Thêm việc đầu tiên nhé!",
               "done": "Chưa hoàn thành việc nào."}
GREETING_HOURS = ((5, "Khuya rồi"), (11, "Chào buổi sáng"), (13, "Chào buổi trưa"), (18, "Chào buổi chiều"), (22, "Chào buổi tối"))
LONG_FIELD_WIDTH = 324
CHART_MIN_WIDTH, COMPACT_HEIGHT = 860, 700
SEARCH_WIDTH, SEARCH_WIDTH_NARROW, SEARCH_NARROW_BELOW = 170, 116, 450
SEARCH_HINT, SEARCH_HINT_NARROW = "Tìm kiếm…   (Ctrl+F)", "Tìm kiếm…"
SAVED_HINT = "Đã lưu, nhập để thay"
TELEGRAM_LABELS = {15: "15p", 30: "30p", 60: "1 giờ", 180: "3 giờ", 360: "6 giờ", 1440: "1 ngày"}


def greeting(hour):
    for limit, phrase in GREETING_HOURS:
        if hour < limit:
            return phrase
    return "Khuya rồi"


class StatStrip(Scaled, tk.Canvas):
    """Bốn con số của hôm nay trên cùng một dải, để phần việc cần làm còn nhiều chỗ. Cả thẻ vẽ trên một Canvas: dựng bằng thẻ,
    ô, nhãn và biểu đồ CustomTkinter là gần 50 cửa sổ Tk. Mỗi ô bấm được để tới danh sách tương ứng, rê chuột thì ô sáng lên."""
    STATS = (("today", "Còn lại hôm nay", "Còn lại", "today"), ("overdue", "Quá hạn", "Quá hạn", "today"),
             ("rate", "Hoàn thành", "Đã xong", "done"), ("week", "7 ngày qua", "7 ngày", "calendar"))
    FONTS = {"number": ("FONT_DISPLAY", 32, 0), "title": ("FONT_SEMIBOLD", 13, 0), "note": ("FONT_TEXT", 12, 0)}
    PAD, NUMBER_LEFT, NUMBER_GAP, NUMBER_HEIGHT, NUMBER_PAD = 4, 10, 8, 48, 4
    TITLE_HEIGHT, NOTE_HEIGHT = 20, 18
    CHART_WIDTH, CHART_HEIGHT, CHART_PAD, CHART_RIGHT = 84, 36, 6, 10

    def __init__(self, master, app):
        super().__init__(master, highlightthickness=0, bd=0)
        self.app = app
        self.fonts = FontCache(self.FONTS)
        self.values = {key: ("0", "", TEXT) for key, *_ in self.STATS}
        self.week = []
        self.hover = None
        self.cells = []  # khung từng ô ở lần vẽ cuối, để biết chuột đang ở ô nào
        self.chart_shown = True
        self.height = 0
        self.bind("<Configure>", lambda _: self._paint())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _: self._set_hover(None))
        self.bind("<Button-1>", self._on_click)
        AppearanceModeTracker.add(lambda _mode: self._paint(), self)
        ScalingTracker.add_widget(self._on_scaling, self)
        self._on_scaling(ScalingTracker.get_widget_scaling(self))

    def _px(self, value):
        return scaled(value, self._scale)

    def _on_scaling(self, scale, _window=None):
        self._scale = scale
        self.fonts.rescale(scale)
        line = lambda name: self.fonts.get(name).metrics("linespace")  # noqa: E731
        self.number_height = max(self._px(self.NUMBER_HEIGHT), line("number"))
        self.title_height = max(self._px(self.TITLE_HEIGHT), line("title"))
        self.note_height = max(self._px(self.NOTE_HEIGHT), line("note"))
        self.cell_height = max(self.number_height + 2 * self._px(self.NUMBER_PAD), self.title_height + self.note_height)
        self.height = self.cell_height + 2 * self._px(self.PAD)
        self.configure(height=self.height)
        self._relayout()
        self._paint()

    def fit(self, width):
        """Cửa sổ hẹp thì bỏ biểu đồ và dùng nhãn ngắn, con số vẫn đủ ý."""
        shown = width >= CHART_MIN_WIDTH
        if shown != self.chart_shown:
            self.chart_shown = shown
            self._paint()

    def show(self, stats):
        overdue, rate = stats["overdue"], stats["rate"]
        values = {"today": (str(stats["today_open"]), f"{stats['done_today']} việc đã xong", TEXT),
                  "overdue": (str(overdue), "Cần xử lý ngay" if overdue else "Không có việc trễ", RED if overdue else GREEN),
                  "rate": ("—" if rate is None else f"{round(rate * 100)}%", f"{stats['done_today']}/{stats['planned']} việc",
                           GREEN if stats["done_today"] else TEXT),
                  "week": (str(sum(count for _, count in stats["week"])), "việc đã xong", TEXT)}
        if values != self.values or stats["week"] != self.week:
            self.values, self.week = values, stats["week"]
            self._paint()

    def _paint(self):
        self.delete("all")
        width, height = self.winfo_width(), self.height
        self.configure(bg=resolve(BG))
        self.cells = []
        if width < 40:
            return
        px = self._px
        rounded(self, 0, 0, width, height, self._px(theme.RADIUS_CARD), resolve(CARD), resolve(BG), outline=resolve(BORDER))
        pad, rule = px(self.PAD), px(1)  # khe 1 điểm ảnh giữa các ô, chỗ của vạch ngăn mà bản CustomTkinter chưa bao giờ vẽ ra
        titles = [title if self.chart_shown else short for _key, title, short, _target in self.STATS]
        want = max(self._wanted(key, title) for (key, *_), title in zip(self.STATS, titles)) + 2 * pad
        left = 0
        for index, (column, (key, *_), title) in enumerate(zip(uniform_columns(width, want, 4, rule), self.STATS, titles)):
            box = (left + pad, pad, left + column - pad, pad + self.cell_height)
            self.cells.append(box)
            self._paint_cell(index, key, title, box)
            left += column + rule

    def _wanted(self, key, title):
        """Bề rộng ô cần để đủ chữ, như ô dựng bằng widget báo cho grid: chia cột theo đó mới khớp từng điểm ảnh."""
        number, note, _color = self.values[key]
        chart = round(self.CHART_WIDTH * self._scale) + self._px(self.CHART_RIGHT) if key == "week" and self.chart_shown else 0
        return (self._px(self.NUMBER_LEFT) + self.fonts.measure("number", number) + self._px(self.NUMBER_GAP)
                + max(self.fonts.measure("title", title), self.fonts.measure("note", note)) + chart)

    def _paint_cell(self, index, key, title, box):
        """Bố cục giống bản dựng bằng widget: số bên trái, nhãn và ghi chú giãn theo chỗ, biểu đồ bên phải ô cuối."""
        px, (x0, y0, x1, _y1) = self._px, box
        back = CARD_HOVER if index == self.hover else CARD
        if index == self.hover:
            rounded(self, *box, self._px(theme.RADIUS_CONTROL), resolve(CARD_HOVER), resolve(CARD))
        number, note, color = self.values[key]
        font = self.fonts.get("number")
        left, pad = x0 + px(self.NUMBER_LEFT), px(self.NUMBER_PAD)
        top = y0 + pad + (self.cell_height - 2 * pad - self.number_height) // 2
        self.create_text(left, top + (self.number_height - font.metrics("linespace")) // 2, text=number, font=font, fill=resolve(color),
                         anchor="nw")
        left += self.fonts.measure("number", number) + px(self.NUMBER_GAP)
        chart = key == "week" and self.chart_shown
        wanted = max(self.fonts.measure("title", title), self.fonts.measure("note", note))
        room, after = side_by_side(x1 - left, wanted, round(self.CHART_WIDTH * self._scale) + px(self.CHART_RIGHT) if chart else 0)
        top = y0 + (self.cell_height - self.title_height - self.note_height) // 2
        for name, content, height, fill in (("title", title, self.title_height, TEXT), ("note", note, self.note_height, MUTED)):
            font = self.fonts.get(name)
            self.create_text(left, top + (height - font.metrics("linespace")) // 2, text=self.fonts.fit(name, content, room), font=font,
                             fill=resolve(fill), anchor="nw")
            top += height
        if chart:
            size, chart_pad, width = round(self.CHART_HEIGHT * self._scale), px(self.CHART_PAD), max(after - px(self.CHART_RIGHT), 0)
            top = y0 + chart_pad + (self.cell_height - 2 * chart_pad - size) // 2
            draw_week(self, x1 - px(self.CHART_RIGHT) - width, top, width, size, self.week, back, self._scale, ("bar",))

    def _cell_at(self, x, y):
        return next((index for index, (x0, y0, x1, y1) in enumerate(self.cells) if x0 <= x < x1 and y0 <= y < y1), None)

    def _on_motion(self, event):
        self._set_hover(self._cell_at(event.x, event.y))

    def _set_hover(self, index):
        if index != self.hover:
            self.hover = index
            self.configure(cursor="hand2" if index is not None else "")
            self._paint()

    def _on_click(self, event):
        index = self._cell_at(event.x, event.y)
        if index is not None:
            self.app.navigate(self.STATS[index][3])


class QuoteCard(Card):
    """Câu nói hôm nay trên Tổng quan: mỗi ngày một câu của kho quotes.py, trong các chủ đề chọn ở Cài đặt, ghi rõ tác giả."""

    def __init__(self, master):
        super().__init__(master)
        self.shown = None
        self.kind = Label(self, text="", font=theme.semibold(13), text_color=ACCENT, anchor="w", height=20)
        self.kind.pack(fill="x", padx=16, pady=(12, 0))
        self.body = Label(self, text="", font=theme.semibold(14), text_color=TEXT, anchor="w", justify="left", height=22, elastic=True)
        self.body.pack(fill="x", padx=16, pady=(2, 0))
        self.author = Label(self, text="", font=theme.text(13), text_color=MUTED, anchor="w", justify="left", height=20, elastic=True)
        self.author.pack(fill="x", padx=16, pady=(4, 12))
        self.bind("<Configure>", self._wrap)

    def _wrap(self, event):
        width = event.width / ScalingTracker.get_widget_scaling(self) - 34
        self.body.configure(wraplength=width)
        self.author.configure(wraplength=width)

    def show(self, day, topics):
        if (day, topics) != self.shown:
            self.shown = (day, topics)
            quote = quotes.for_day(day, topics)
            self.kind.configure(text=f"Câu nói hôm nay · {quote.label}")
            self.body.configure(text=f"“{quote.text}”")
            self.author.configure(text=f"— {quote.author}")


class FocusCard(Card):
    """Thẻ đếm ngược time-blocking."""

    def __init__(self, master, app, dashboard):
        super().__init__(master)
        self.app = app
        self.dashboard = dashboard
        self.current_id = None
        self.block = None
        self.heading = Label(self, text="Tập trung", font=theme.semibold(16), text_color=TEXT, anchor="w", height=26)
        self.heading.pack(fill="x", padx=16, pady=(12, 0))
        self.parts = Plain(self)  # CTk gọi lại lệnh pack mỗi khi đổi cỡ chữ, nên "before" phải trỏ tới khung luôn còn đó
        self.parts.pack(fill="x", padx=16, pady=(4, 14))
        self._build_active()
        self._build_idle()
        self.shown = self.idle
        self._show(self.active)

    def _show(self, part):
        if part is not self.shown:
            self.shown.pack_forget()
            part.pack(fill="x")
            self.shown = part

    def set_compact(self, compact):
        """Cửa sổ thấp thì bỏ tiêu đề: đồng hồ đã tự nói thẻ này để làm gì."""
        if compact:
            self.heading.pack_forget()
            self.parts.pack(fill="x", padx=16, pady=(12, 14))
        else:
            self.heading.pack(fill="x", padx=16, pady=(12, 0), before=self.parts)
            self.parts.pack(fill="x", padx=16, pady=(4, 14))

    def _build_active(self):
        self.active = Plain(self.parts)
        self.active_title = FitLabel(self.active, font=theme.text(13), text_color=MUTED, anchor="w", height=20)
        self.active_title.pack(fill="x")
        self.clock = Label(self.active, text="00:00", font=theme.display(48), text_color=ACCENT, anchor="w", height=64)
        self.clock.pack(fill="x")
        self.progress = ctk.CTkProgressBar(self.active, height=6, corner_radius=3, fg_color=TRACK, progress_color=ACCENT)
        self.progress.pack(fill="x", pady=(2, 10))
        self.progress.bind("<Configure>", lambda _: setattr(self, "progress_step", None), add="+")
        self.progress_step = None
        buttons = Plain(self.active)
        buttons.pack(fill="x")
        secondary_button(buttons, "+5p", self._extend, width=44).pack(side="left")
        secondary_button(buttons, "Kết thúc", self._finish, width=64).pack(side="left", padx=(6, 0))
        primary_button(buttons, "Hoàn thành", self._complete).pack(side="left", fill="x", expand=True, padx=(6, 0))

    def _build_idle(self):
        self.idle = Plain(self.parts)
        self.idle_text = Label(self.idle, text="", font=theme.text(13), text_color=MUTED, anchor="w", justify="left", elastic=True)
        self.idle_text.pack(fill="x")
        self.idle.bind("<Configure>", self._wrap_idle_text)
        self.presets = Plain(self.idle)
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
            self._show(self.active)
            self.active_title.set_text(block[0]["title"])
            self.block = block
            self.tick(now)
            return
        self.block = None
        self._show(self.idle)
        selected = self.app.store.get_task(self.dashboard.selected_id) if self.dashboard.selected_id else None
        coming = next_block(tasks, now)
        lines = []
        if selected and not selected["done_at"]:
            lines.append(f"Bắt đầu đếm ngược cho: {selected['title']}")
        else:
            lines.append("Chọn một việc trong danh sách, rồi chọn thời lượng để bắt đầu đếm ngược.")
        if coming:
            lines.append(f"Khối tiếp theo {coming[1]:%H:%M}: {coming[0]['title']} (sau {humanize(coming[1] - now)})")
        set_label(self.idle_text, text="\n".join(lines))

    def tick(self, now):
        if not self.block:
            return
        task, start, end = self.block
        if now >= end:
            self.dashboard.app.refresh()
            return
        set_label(self.clock, text=countdown(end - now))
        value = min(max((end - now) / (end - start), 0), 1)
        step = round(value * self.progress.winfo_width())
        if step != self.progress_step:  # khối 50 phút chỉ dịch 1 điểm ảnh mỗi chục giây, không vẽ lại thanh mỗi giây
            self.progress_step = step
            self.progress.set(value)


class Dashboard(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=BG)
        self.app = app
        self.store = app.store
        self.selected_id = None
        self.deadline = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        self.compact = False
        self.bind("<Configure>", self._fit)

        header = Plain(self)
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 10))
        self.hello = Label(header, text="", font=theme.display(24), text_color=TEXT, anchor="w", height=36)
        self.hello.pack(fill="x")
        self.today_label = FitLabel(header, font=theme.text(13), text_color=MUTED, anchor="w", height=20, cursor="hand2")
        self.today_label.pack(fill="x")
        self.today_label.bind("<Button-1>", lambda _: app.navigate("almanac"))

        self.quick = QuickEntry(self, app)
        self.quick.grid(row=1, column=0, sticky="ew", padx=24)

        self.stats = StatStrip(self, app)
        self.stats.grid(row=2, column=0, sticky="ew", padx=24, pady=(8, 10))

        band = Card(self)
        band.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 10))
        self.band_title = Label(band, text="", font=theme.text(13), text_color=MUTED, anchor="w", height=20)
        self.band_title.pack(fill="x", padx=14, pady=(8, 2))
        self.band = DayBand(band, app)
        self.band.pack(fill="x", padx=12, pady=(0, 10))

        body = Plain(self)
        body.grid(row=4, column=0, sticky="nsew", padx=24, pady=(0, 20))
        body.grid_columnconfigure(0, weight=3, uniform="body")
        body.grid_columnconfigure(1, weight=2, uniform="body")
        body.grid_rowconfigure(0, weight=1)

        tasks_column = Plain(body)
        tasks_column.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        Label(tasks_column, text="Việc cần làm hôm nay", font=theme.semibold(16), text_color=TEXT, anchor="w", height=26).pack(fill="x", padx=4)
        self.task_list = TaskList(tasks_column, app, self._select, app.open_task, EMPTY_TEXTS["today"])
        self.task_list.pack(fill="both", expand=True)

        side = Plain(body)
        side.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.focus_card = FocusCard(side, app, self)
        self.focus_card.pack(fill="x")
        agenda = Card(side)
        agenda.pack(fill="x", pady=(10, 0))
        Label(agenda, text="Mốc tiếp theo", font=theme.semibold(16), text_color=TEXT, anchor="w", height=26).pack(
            fill="x", padx=16, pady=(12, 0))
        self.deadline_title = FitLabel(agenda, font=theme.text(13), text_color=MUTED, anchor="w", height=20)
        self.deadline_title.pack(fill="x", padx=16)
        self.deadline_clock = Label(agenda, text="", font=theme.display(24), text_color=TEXT, anchor="w", height=36)
        self.deadline_clock.pack(fill="x", padx=16, pady=(0, 8))
        self.saying = QuoteCard(side)
        self.saying.pack(fill="x", pady=(10, 0))

    def _fit(self, event):
        """Cửa sổ thấp thì bớt phần phụ để danh sách việc và đồng hồ không bị cắt."""
        scale = ScalingTracker.get_widget_scaling(self)
        self.stats.fit(event.width / scale)
        compact = event.height / scale < COMPACT_HEIGHT
        if compact != self.compact:
            self.compact = compact
            self.focus_card.set_compact(compact)
            if compact:
                self.band_title.pack_forget()
                self.saying.pack_forget()
            else:
                self.band_title.pack(fill="x", padx=14, pady=(8, 2), before=self.band)
                self.saying.pack(fill="x", pady=(10, 0))

    def _select(self, task_id):
        self.selected_id = task_id
        self.focus_card.refresh(self.store.scheduled_tasks(), datetime.now())

    def refresh(self, now):
        reading = daybook.read_day(now.date())
        set_label(self.hello, text=f"{greeting(now.hour)}, {WEEKDAY_LONG[now.weekday()].lower()} {now.day} tháng {now.month}")
        marks = ", ".join(mark.name for mark in reading.marks[:3])
        self.today_label.set_text(f"{lunar_text(solar_to_lunar(now.date()))} âm lịch · {reading.title}" + (f", phạm {marks}" if marks else ""))
        self.stats.show(self.app.stats)
        self.task_list.set_entries(group_entries(self.store.list_tasks("today", now), now, "today", self.store.list_tasks("done_today", now)))
        self.task_list.select(self.selected_id)
        tasks = self.store.scheduled_tasks()
        self.focus_card.refresh(tasks, now)
        self.deadline = self.store.nearest_deadline(now)
        self.deadline_title.set_text(self.deadline["title"] if self.deadline else "Không có hạn nào sắp tới")
        if not self.deadline:
            set_label(self.deadline_clock, text="")
        good = ", ".join(slot.name for slot in daybook.hours_of(now.date()) if slot.good)
        set_label(self.band_title, text=f"Giờ hoàng đạo hôm nay: {good}")
        self.band.show(now, tasks, self.store.blocks_today(now))
        self.saying.show(now.date(), quotes.chosen_topics(self.store.setting("quote_topics")))
        self.tick(now)

    def tick(self, now):
        self.focus_card.tick(now)
        if self.deadline:
            due = from_text(self.deadline["due_at"])
            left = due - now
            if left.total_seconds() <= 0:
                self.app.refresh()
                return
            if self.deadline["all_day"]:
                text = "Hết hôm nay" if due.date() == now.date() else f"{due:%d/%m}, còn {(due.date() - now.date()).days} ngày"
            else:
                text = f"{left.days} ngày {countdown(left - timedelta(days=left.days))}" if left.days else countdown(left)
            set_label(self.deadline_clock, text=text, text_color=AMBER if left < timedelta(hours=1) else TEXT)


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
        self.title_text = ""
        self.search_narrow = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        Plain(self, width=24, height=1).grid(row=0, column=2)  # lề phải giữ nguyên dù panel chi tiết đóng hay mở

        self.header = header = Plain(self)
        header.grid(row=0, column=0, sticky="ew", padx=(24, 0), pady=(18, 8))
        header.bind("<Configure>", self._fit_header)
        self.search = field(header, width=SEARCH_WIDTH, placeholder_text=SEARCH_HINT)
        self.search.pack(side="right")  # xếp trước để không bị bóp khi thiếu chỗ
        self.search.bind("<KeyRelease>", self._on_search)
        self.title_label = Label(header, text="", font=theme.display(24), text_color=TEXT, anchor="w", height=36)
        self.title_label.pack(side="left")
        self.count_label = Label(header, text="", font=theme.text(14), text_color=MUTED, height=34)
        self.count_label.pack(side="left", padx=(10, 0), pady=(4, 0))

        self.quick = QuickEntry(self, app)
        self.quick.grid(row=1, column=0, sticky="ew", padx=(24, 0))

        self.task_list = TaskList(self, app, self._select)
        self.task_list.grid(row=2, column=0, sticky="nsew", padx=(24, 0), pady=(4, 20))

    def show_view(self, view, tag_id=0, tag_name=""):
        self.view, self.tag_id, self.tag_name = view, tag_id, tag_name
        set_text(self.search, "")
        self.search_text = ""
        self.refresh(datetime.now())

    def _fit_header(self, _event=None):
        """Panel chi tiết mở trên cửa sổ nhỏ thì ô tìm kiếm thu lại, tên dài (như tên tag) tự cắt bằng dấu ba chấm."""
        scale = ScalingTracker.get_widget_scaling(self)
        width = self.header.winfo_width()
        narrow = width / scale < SEARCH_NARROW_BELOW
        if narrow != self.search_narrow:
            self.search_narrow = narrow
            self.search.configure(width=SEARCH_WIDTH_NARROW if narrow else SEARCH_WIDTH, placeholder_text=SEARCH_HINT_NARROW if narrow else SEARCH_HINT)
        room = width - round(((SEARCH_WIDTH_NARROW if narrow else SEARCH_WIDTH) + 16) * scale) - self.count_label.winfo_reqwidth() - round(10 * scale)
        font = theme.display(24)
        shown = fit_text(lambda piece: measure_text(font, scale, piece), self.title_text, room) if room > 0 else self.title_text
        set_label(self.title_label, text=shown)

    def refresh(self, now):
        self.title_text = self.tag_name or VIEW_TITLES[self.view]
        tasks = self.store.list_tasks(self.view, now, self.tag_id, self.search_text)
        self.count_label.configure(text=str(len(tasks)) if tasks else "")
        self._fit_header()
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
        """Mở panel thì cả vùng nội dung mờ dần, đổi việc khi panel đang mở thì chỉ panel mờ dần."""
        opening = not self.editor_open
        with self.app.fade(None if opening else self.editor, when=opening or task_id != self.editor.task_id):
            self._open_editor(task_id)

    def _open_editor(self, task_id):
        if self.editor is None:
            self.editor = TaskEditor(self, self.app)
        if not self.editor_open:
            self.editor.grid(row=0, column=1, rowspan=3, sticky="ns", padx=(12, 0), pady=(18, 20))
            self.editor_open = True
        self.task_list.select(task_id)
        self.editor.load(task_id)

    def close_editor(self):
        with self.app.fade(when=self.editor_open):
            self._close_editor()

    def _close_editor(self):
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
        self.brief_status = None
        self.brief_status_shown = None
        header = Plain(self)
        header.pack(fill="x", padx=24, pady=(18, 10))
        self.tabs = segmented(header, list(SETTING_TABS), self._show_tab, dynamic_resizing=False, width=360)
        self.tabs.pack(side="right")
        Label(header, text="Cài đặt", font=theme.display(24), text_color=TEXT, anchor="w", height=36).pack(side="left")
        scroll = motion.ScrollFrame(self, BG)
        scroll.pack(fill="both", expand=True, padx=(16, 8), pady=(0, 16))
        self.scroll = scroll
        self.pages = {name: Plain(scroll) for name in SETTING_TABS}
        self.builders = dict(zip(SETTING_TABS, (self._build_general, self._build_notices, self._build_telegram, self._build_ai)))
        self.tab = None
        self._show_tab(SETTING_TABS[0])

    def _build_general(self):
        section = self._section("Giao diện")
        row = self._row(section, "Chủ đề màu", "Tối là nền đen, nhấn xanh dương, độ tương phản cao")
        labels = {"Tối": "dark", "Sáng": "light", "Hệ thống": "system"}
        self.theme_choice = segmented(row, list(labels), lambda label: self._set_theme(labels[label]))
        self.theme_choice.pack(side="right")
        self.theme_choice.set(next(k for k, v in labels.items() if v == self.store.setting("theme")))
        row = self._row(section, "Cỡ chữ", "Phóng to chữ và khoảng cách trong toàn bộ cửa sổ")
        self.text_choice = segmented(row, list(theme.TEXT_SCALES), lambda label: self.app.set_text_scale(theme.TEXT_SCALES[label]))
        self.text_choice.pack(side="right")
        self.text_choice.set(next(k for k, v in theme.TEXT_SCALES.items() if v == self.store.setting("text_scale")))

        section = self._section("Câu nói hôm nay")
        Label(section, text="Chủ đề", font=theme.text(14), text_color=TEXT, anchor="w", height=22).pack(fill="x", padx=16, pady=(10, 0))
        total = sum(len(items) for *_, items in quotes.TOPICS)
        note = Label(section, text=f"{total} câu chia {len(quotes.TOPICS)} chủ đề. Mỗi ngày Tổng quan hiện một câu ngẫu nhiên trong các chủ đề "
                     "đang chọn, ghi rõ tác giả", font=theme.text(12), text_color=MUTED, anchor="w", justify="left", height=18, elastic=True)
        note.pack(fill="x", padx=16)
        section.bind("<Configure>", lambda event: self._wrap(note, event.width - round(32 * ScalingTracker.get_widget_scaling(self))), add="+")
        chips = Plain(section)
        chips.pack(fill="x", padx=16, pady=(8, 12))
        chosen = quotes.chosen_topics(self.store.setting("quote_topics"))
        self.topic_chips = {}
        for index, (key, _name, label, _items) in enumerate(quotes.TOPICS):  # chip là một Canvas, sáu dòng công tắc là gần 60 cửa sổ Tk
            chip = Chip(chips, label, lambda key=key: self._toggle_topic(key))
            chip.set_active(key in chosen)
            chip.grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 6), pady=(0, 6))
            self.topic_chips[key] = chip

        section = self._section("Tag")
        self.tag_rows = Plain(section)
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

        section = self._section("Dữ liệu")
        row = self._row(section, "Thư mục dữ liệu", DATA_DIR if len(DATA_DIR) <= 72 else "…" + DATA_DIR[-71:])
        secondary_button(row, "Mở thư mục", lambda: os.startfile(DATA_DIR), width=104).pack(side="right")
        Label(self.page, text=f"{APP_NAME} {__version__}", font=theme.text(12), text_color=MUTED, anchor="w").pack(
            fill="x", padx=8, pady=(10, 0))

    def _build_notices(self):
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

    def _show_tab(self, name):
        """Mỗi tab chỉ được dựng khi mở lần đầu: cả bốn tab có gần 400 widget mà thường chỉ cần một."""
        with self.app.fade(when=self.tab is not None and name != self.tab):
            self._switch_tab(name)

    def _switch_tab(self, name):
        self.tab = name
        self.tabs.set(name)
        if name in self.builders:
            self.page = self.pages[name]
            self.builders.pop(name)()
        for page in self.pages.values():
            page.pack_forget()
        self.pages[name].pack(fill="x")
        self.scroll.scroller.halt()
        self.scroll._parent_canvas.yview_moveto(0)

    def _build_telegram(self):
        store = self.store
        section = self._section("Bot Telegram")
        row = self._row(section, "Bản tin mỗi ngày", "Thần dâng tờ tấu lên Bệ hạ qua Telegram, mỗi ngày một lần")
        self._switch(row, store.setting("telegram_enabled") == "1", self._set_brief_enabled)
        row = self._row(section, "Nhận tin nhắn và lệnh", "Nhắn việc cho bot, mỗi dòng một việc; /rp, /today, /week để xem tình hình. "
                        "PC cần đang bật và TodoLite đang chạy")
        self._switch(row, store.setting("telegram_inbox") == "1", self._set_inbox)
        row = self._row(section, "Nhắc trước hạn", "Bot nhắn trước hạn chót của việc có giờ. Chọn được nhiều mốc, bỏ chọn hết là tắt")
        self.telegram_chips = {}
        chosen = parse_offsets(store.setting("telegram_remind"))
        for minutes in reversed(TELEGRAM_CHOICES):
            chip = Chip(row, TELEGRAM_LABELS[minutes], lambda m=minutes: self._toggle_telegram_remind(m), width=48)
            chip.set_active(minutes in chosen)
            chip.pack(side="right", padx=(6, 0))
            self.telegram_chips[minutes] = chip
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
        self.brief_status = Label(section, text="", font=theme.text(12), text_color=MUTED, anchor="w", justify="left", wraplength=620, elastic=True)
        self.brief_status.pack(fill="x", padx=16, pady=(0, 10))
        section.bind("<Configure>", lambda event: self._wrap(self.brief_status, event.width - round(32 * ScalingTracker.get_widget_scaling(self))),
                     add="+")
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
        Label(self.page, text=title, font=theme.semibold(16), text_color=TEXT, anchor="w", height=26).pack(
            fill="x", padx=8, pady=(10, 4))
        card = Card(self.page)
        card.pack(fill="x", padx=(8, 8), pady=(0, 6))
        return card

    def _row(self, card, title, note):
        """Một dòng cài đặt, trả về khung bên phải để đặt điều khiển. Khung phải giữ đủ chỗ, ghi chú dài thì tự xuống dòng."""
        row = Plain(card)
        row.pack(fill="x", padx=16, pady=8)
        row.grid_columnconfigure(0, weight=1)
        labels = Plain(row)
        labels.grid(row=0, column=0, sticky="ew", padx=(0, 16))
        Label(labels, text=title, font=theme.text(14), text_color=TEXT, anchor="w", height=22).pack(fill="x")
        hint = Label(labels, text=note, font=theme.text(12), text_color=MUTED, anchor="w", justify="left", height=18, elastic=True)
        hint.pack(fill="x")
        labels.bind("<Configure>", lambda event: self._wrap(hint, event.width))
        controls = Plain(row)
        controls.grid(row=0, column=1, sticky="e")
        return controls

    def _wrap(self, label, width):
        set_label(label, wraplength=round(width / ScalingTracker.get_widget_scaling(self)))

    def _switch(self, row, value, command):
        switch = ctk.CTkSwitch(row, text="", width=44, progress_color=FILL, fg_color=theme.SWITCH_OFF, button_color=theme.SWITCH_KNOB,
                               button_hover_color=theme.SWITCH_KNOB, command=lambda: command(switch.get() == 1))
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
        row = Plain(self.tag_rows)
        row.pack(fill="x", pady=(0, 6))
        tag_id, color = tag["id"], tag["color"]
        ctk.CTkButton(row, text="", width=24, height=24, corner_radius=12, fg_color=color, hover_color=color,
                      command=lambda: self._next_color(tag_id, color)).pack(side="left", padx=(0, 10))
        name = field(row, height=30)
        set_text(name, tag["name"])
        name.pack(side="left", fill="x", expand=True)
        name.bind("<Return>", lambda _: self._rename_tag(tag_id, name))
        name.bind("<FocusOut>", lambda _: self._rename_tag(tag_id, name))
        Label(row, text=f"{tag['n']} việc" if tag["n"] else "", width=60, font=theme.text(12), text_color=MUTED).pack(side="left", padx=(8, 0))
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
        with self.app.fade(self.app):
            self.store.set_setting("theme", value)
            self.app.set_theme(value)
            self.app.apply_caption_color()

    def _set_autostart(self, enabled):
        integration.set_autostart(enabled)

    def _toggle_topic(self, key):
        chip = self.topic_chips[key]
        if chip.active and sum(item.active for item in self.topic_chips.values()) == 1:
            self.app.snackbar.show("Cần giữ ít nhất một chủ đề")  # bỏ hết thì không còn câu nào để hiện
            return
        chip.set_active(not chip.active)
        self.store.set_setting("quote_topics", ",".join(name for name, item in self.topic_chips.items() if item.active))
        self.app.changed()

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

    def _toggle_telegram_remind(self, minutes):
        chip = self.telegram_chips[minutes]
        chip.set_active(not chip.active)
        chosen = [str(value) for value in TELEGRAM_CHOICES if self.telegram_chips[value].active]
        self.store.set_setting("telegram_remind", ",".join(reversed(chosen)))
        self.app.changed()  # agent tính lại mốc thức dậy

    # ---------- Bot Telegram và AI ----------

    def refresh(self, _now):
        status = self.store.setting("telegram_status")
        if self.brief_status is not None and status != self.brief_status_shown:
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
            self.store.set_setting("telegram_commands", "")  # bot mới chưa có menu lệnh
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

    def _set_inbox(self, enabled):
        if enabled:
            self.store.set_setting("telegram_inbox_since", int(time.time()))  # tin nhắn lúc tắt không thành việc
        self._set_flag("telegram_inbox", enabled)

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
        from ..bot import Bot
        token, url = self.store.secret("telegram_token"), self.store.setting("telegram_api_url")
        return lambda: Bot(token, url)

    def _check_bot(self):
        from ..web import ApiError
        make_bot = self._bot_maker()
        self._show_brief_status("Đang kiểm tra…")

        def check():
            bot = make_bot()
            name = bot.me()
            try:
                bot.set_commands()  # kiểm tra xong là có ngay menu lệnh khi gõ "/" trong Telegram
            except ApiError:
                return name, False
            return name, True
        self._in_background(self.check_button, check, self._on_checked)

    def _on_checked(self, result, error):
        name, menu = result or (None, False)
        if menu:
            from ..bot import COMMANDS_VERSION
            self.store.set_setting("telegram_commands", COMMANDS_VERSION)
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
