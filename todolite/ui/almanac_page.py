"""Trang Vạn niên: lịch âm dương, can chi, giờ và ngày hoàng đạo, tiết khí, ngày lễ, hỏi đáp tử vi.

Lưới tháng nằm trên một Canvas như các trang lịch khác. Phần Tử vi chỉ dựng khi mở lần đầu,
còn thư viện mạng chỉ nạp khi thật sự gọi AI.
"""
import queue
import threading
import tkinter as tk
import traceback
from datetime import date, datetime, timedelta

import customtkinter as ctk
from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import AppearanceModeTracker
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from .. import ai, almanac, lunar
from ..paths import log
from ..schedule import WEEKDAY_LONG, WEEKDAY_SHORT, calendar_items, days_in_month, month_days
from . import theme
from .calendar import QuickPopover, add_on_day
from .theme import (ACCENT, ACCENT_SOFT, AMBER, BG, BORDER, CARD, CARD_HOVER, FILL, GREEN, GREEN_SOFT, Icon, MUTED, ON_FILL, RED, RED_SOFT,
                    TEXT, TRACK, blend, resolve)
from .widgets import Card, DatePicker, FontCache, IconButton, field, primary_button, secondary_button, segmented, set_text

TABS = ("Lịch", "Tử vi")
MIN_YEAR, MAX_YEAR = 1800, 2199  # khoảng đã đối chiếu thuật toán lịch
PANEL_WIDTH = 300
SIDE_WIDTH = 270
MAX_DAY_TASKS = 5
POLL_MS = 60


def parse_date(text):
    try:
        day = datetime.strptime(text.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None
    return day if MIN_YEAR <= day.year <= MAX_YEAR else None


class MonthGrid(tk.Canvas):
    """Lưới tháng dương kèm ngày âm. Chấm vàng là ngày lễ, chấm xanh là ngày có việc."""
    HEAD = 30
    FONTS = {"head": ("FONT_SEMIBOLD", 12, 0), "solar": ("FONT_SEMIBOLD", 17, 0), "lunar": ("FONT_TEXT", 11, 0),
             "badge": ("FONT_ICON", 32, 0), "dot": ("FONT_ICON", 7, 0)}

    def __init__(self, master, page):
        super().__init__(master, highlightthickness=0, bd=0, bg=resolve(CARD), takefocus=1, cursor="hand2")
        self.page = page
        self.selected = date.today()
        self.year, self.month = self.selected.year, self.selected.month
        self.event_days = self.task_days = frozenset()
        self.hover = None
        self.layout = (0, 1, 1, ())
        self.scale = 1.0
        self.fonts = FontCache(self.FONTS)
        self.draw_pending = False

        self.bind("<Configure>", lambda _: self.schedule_draw())
        self.bind("<Motion>", lambda event: self._set_hover(self._day_at(event.x, event.y)))
        self.bind("<Leave>", lambda _: self._set_hover(None))
        self.bind("<Button-1>", self._on_click)
        self.bind("<MouseWheel>", lambda event: self.page.step_month(-1 if event.delta > 0 else 1))
        for key, days in (("<Left>", -1), ("<Right>", 1), ("<Up>", -7), ("<Down>", 7)):
            self.bind(key, lambda _event, step=days: self.page.select(self.selected + timedelta(days=step)))
        self.bind("t", lambda _: self.page.go_today())
        AppearanceModeTracker.add(lambda _mode: self._on_theme(), self)

    def _on_theme(self):
        self.configure(bg=resolve(CARD))
        self.schedule_draw()

    def schedule_draw(self):
        if not self.draw_pending:
            self.draw_pending = True
            self.after_idle(self._paint)

    def _paint(self):
        self.draw_pending = False
        if not self.winfo_exists():
            return
        self.delete("all")
        self.scale = ScalingTracker.get_widget_scaling(self)
        self.fonts.rescale(self.scale)
        width, height = self.winfo_width(), self.winfo_height()
        if width < 60 or height < 60:
            return
        days = month_days(self.year, self.month)
        head = round(self.HEAD * self.scale)
        cell_w, cell_h = width / 7, (height - head) / (len(days) // 7)
        self.layout = (head, cell_w, cell_h, days)
        colors = {name: resolve(pair) for name, pair in (("card", CARD), ("hover", CARD_HOVER), ("border", BORDER), ("text", TEXT),
                                                         ("muted", MUTED), ("accent", ACCENT), ("fill", FILL), ("on_fill", ON_FILL),
                                                         ("red", RED), ("amber", AMBER))}
        for column, name in enumerate(WEEKDAY_SHORT):
            self.create_text((column + 0.5) * cell_w, head / 2, text=name, font=self.fonts.get("head"),
                             fill=colors["red" if column == 6 else "muted"])
        today = date.today()
        for index, day in enumerate(days):
            self._paint_cell(day, index % 7 * cell_w, head + index // 7 * cell_h, cell_w, cell_h, colors, today)

    def _paint_cell(self, day, x, y, width, height, colors, today):
        inset = round(2 * self.scale)
        box = (x + inset, y + inset, x + width - inset, y + height - inset)
        if day == self.selected:
            self.create_rectangle(*box, outline=colors["accent"], fill=blend(colors["fill"], colors["card"], 0.16))
        elif day == self.hover:
            self.create_rectangle(*box, outline="", fill=colors["hover"])
        middle = x + width / 2
        number_y = y + height * 0.40
        if day == today:
            self.create_text(middle, number_y, text=Icon.DOT, font=self.fonts.get("badge"), fill=colors["fill"])
            color = colors["on_fill"]
        elif day.month != self.month:
            color = colors["muted"]
        else:
            color = colors["red" if day.weekday() == 6 else "text"]
        self.create_text(middle, number_y, text=str(day.day), font=self.fonts.get("solar"), fill=color)
        label = lunar.lunar_label(day)
        self.create_text(middle, y + height * 0.76, text=label, font=self.fonts.get("lunar"),
                         fill=colors["accent" if "/" in label else "muted"])
        dot_y = y + round(10 * self.scale)
        if day in self.event_days:
            self.create_text(x + width - round(9 * self.scale), dot_y, text=Icon.DOT, font=self.fonts.get("dot"), fill=colors["amber"])
        if day in self.task_days:
            self.create_text(x + round(9 * self.scale), dot_y, text=Icon.DOT, font=self.fonts.get("dot"), fill=colors["accent"])

    def _day_at(self, x, y):
        head, cell_w, cell_h, days = self.layout
        if y < head or not days:
            return None
        index = int((y - head) // cell_h) * 7 + min(int(x // cell_w), 6)
        return days[index] if 0 <= index < len(days) else None

    def _set_hover(self, day):
        if day != self.hover:
            self.hover = day
            self.schedule_draw()

    def _on_click(self, event):
        self.focus_set()
        day = self._day_at(event.x, event.y)
        if day:
            self.page.select(day)


class EventList(Card):
    """Các ngày lễ trong tháng, bấm một dòng để tới ngày đó."""

    def __init__(self, master, page):
        super().__init__(master)
        self.page = page
        self.signature = None
        self.title = ctk.CTkLabel(self, text="", font=theme.semibold(14), text_color=TEXT, anchor="w", height=24)
        self.title.pack(fill="x", padx=14, pady=(8, 0))
        self.text = ctk.CTkTextbox(self, height=108, corner_radius=0, fg_color="transparent", text_color=TEXT, font=theme.text(13),
                                   wrap="word", activate_scrollbars=False, cursor="arrow", state="disabled", takefocus=0)
        self.text.pack(fill="x", padx=(10, 4), pady=(0, 8))
        self.text.configure(tabs=(round(52 * ScalingTracker.get_widget_scaling(self)),))
        self._paint_tags()
        AppearanceModeTracker.add(lambda _mode: self._paint_tags(), self)

    def _paint_tags(self):
        self.text.tag_config("date", foreground=resolve(ACCENT))
        self.text.tag_config("muted", foreground=resolve(MUTED))

    def show(self, month, events):
        if (month, events) == self.signature:
            return
        self.signature = (month, events)
        self.title.configure(text=f"Sự kiện tháng {month}")
        text = self.text
        text.configure(state="normal")
        text.delete("1.0", "end")
        if not events:
            text.insert("end", f"Không có sự kiện nổi bật trong tháng {month}.", "muted")
        for index, (day, name) in enumerate(events):
            tag = f"event{index}"
            text.insert("end", f"{day:%d/%m}", ("date", tag))
            text.insert("end", f"\t{name}\n", tag)
            text.tag_bind(tag, "<Button-1>", lambda _event, target=day: self.page.select(target))
        text.configure(state="disabled")


class DayPanel(ctk.CTkScrollableFrame):
    """Mọi thông tin của ngày đang chọn, và ô đổi ngày âm sang dương."""

    def __init__(self, master, page):
        super().__init__(master, width=PANEL_WIDTH, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER,
                         scrollbar_button_color=TRACK, scrollbar_button_hover_color=MUTED)
        self.page = page
        self.task_signature = None
        self._build_summary()
        self._build_hours()
        self.events = self._section("Ngày lễ")
        self._heading("Việc trong ngày")
        self.task_rows = ctk.CTkFrame(self, fg_color="transparent")
        self.task_rows.pack(fill="x", padx=12)
        self.saying = self._section("Tục ngữ hôm nay")
        self._build_converter()

    def _block(self, pady=(0, 0)):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=12, pady=pady)
        return frame

    def _note(self, master, color=MUTED):
        return ctk.CTkLabel(master, text="", font=theme.text(13), text_color=color, anchor="w", justify="left", wraplength=PANEL_WIDTH - 24)

    def _heading(self, title):
        ctk.CTkLabel(self, text=title, font=theme.semibold(13), text_color=TEXT, anchor="w", height=20).pack(fill="x", padx=12, pady=(10, 0))

    def _section(self, title):
        self._heading(title)
        note = self._note(self)
        note.pack(fill="x", padx=12)
        return note

    def _build_summary(self):
        top = self._block(pady=(8, 0))
        self.add_button = secondary_button(top, "+ Thêm việc", self.page.add_task, width=92, height=28)
        self.add_button.pack(side="right")
        self.weekday = ctk.CTkLabel(top, text="", font=theme.semibold(14), text_color=ACCENT, height=28)
        self.weekday.pack(side="left")
        solar = self._block()
        self.solar_day = ctk.CTkLabel(solar, text="", font=theme.display(54), text_color=TEXT, height=66)
        self.solar_day.pack(side="left")
        self.solar_month = ctk.CTkLabel(solar, text="", font=theme.text(14), text_color=MUTED, justify="left", anchor="w")
        self.solar_month.pack(side="left", padx=(12, 0))
        self.lunar_day = ctk.CTkLabel(self, text="", font=theme.display(20), text_color=TEXT, anchor="w", height=28)
        self.lunar_day.pack(fill="x", padx=12)
        self.lunar_note = ctk.CTkLabel(self, text="", font=theme.text(13), text_color=MUTED, anchor="w", height=20)
        self.lunar_note.pack(fill="x", padx=12)
        tiles = self._block(pady=(8, 0))
        tiles.grid_columnconfigure((0, 1, 2), weight=1, uniform="tile")
        self.tiles = []
        for column, title in enumerate(("Ngày", "Tháng", "Năm")):
            tile = ctk.CTkFrame(tiles, fg_color=ACCENT_SOFT, corner_radius=8)
            tile.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 3, 0 if column == 2 else 3))
            ctk.CTkLabel(tile, text=title, font=theme.text(11), text_color=MUTED, height=16).pack(pady=(5, 0))
            value = ctk.CTkLabel(tile, text="", font=theme.semibold(13), text_color=TEXT, height=20)
            value.pack(pady=(0, 5))
            self.tiles.append(value)
        self.spirit = ctk.CTkLabel(self, text="", font=theme.semibold(13), height=28, corner_radius=8)
        self.spirit.pack(fill="x", padx=12, pady=(8, 0))
        self.term = self._note(self, TEXT)
        self.term.pack(fill="x", padx=12, pady=(6, 0))

    def _build_hours(self):
        self._heading("Giờ hoàng đạo")
        grid = self._block(pady=(2, 0))
        grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="hour")
        self.hours = []
        for index in range(6):
            label = ctk.CTkLabel(grid, text="", font=theme.text(12), text_color=TEXT, height=24, corner_radius=6, fg_color=theme.FIELD)
            label.grid(row=index // 3, column=index % 3, sticky="ew", padx=(0 if index % 3 == 0 else 2, 0 if index % 3 == 2 else 2), pady=2)
            self.hours.append(label)
        self.first_hour = self._note(self)
        self.first_hour.pack(fill="x", padx=12)

    def _build_converter(self):
        self._heading("Đổi ngày âm sang dương")
        row = self._block(pady=(2, 0))
        self.lunar_fields = [field(row, width=width, height=30, justify="center", placeholder_text=hint)
                             for hint, width in (("Ngày", 54), ("Tháng", 58), ("Năm", 66))]
        for entry in self.lunar_fields:
            entry.pack(side="left", padx=(0, 4))
            entry.bind("<Return>", lambda _: self._convert())
        secondary_button(row, "Đổi", self._convert, width=48, height=30).pack(side="right")
        self.leap = ctk.CTkCheckBox(self, text="Tháng nhuận", font=theme.text(13), text_color=TEXT, checkbox_width=18, checkbox_height=18,
                                    corner_radius=5, border_width=1, border_color=MUTED, fg_color=FILL, hover_color=theme.FILL_HOVER)
        self.leap.pack(fill="x", padx=12, pady=(6, 0))
        self.result = self._note(self)
        self.result.pack(fill="x", padx=12, pady=(2, 10))

    def _convert(self):
        try:
            day, month, year = (int(entry.get()) for entry in self.lunar_fields)
        except ValueError:
            self.result.configure(text="Hãy nhập đủ ngày, tháng và năm âm lịch", text_color=RED)
            return
        solar = lunar.lunar_to_solar(day, month, year, self.leap.get() == 1) if MIN_YEAR <= year <= MAX_YEAR else None
        if solar is None:
            self.result.configure(text="Không có ngày âm này", text_color=RED)
            return
        self.page.select(solar)
        self.result.configure(text=f"{WEEKDAY_LONG[solar.weekday()]}, {solar:%d/%m/%Y}", text_color=ACCENT)

    def show(self, day, tasks):
        converted = lunar.solar_to_lunar(day)
        spirit, good = lunar.day_spirit(day)
        next_term, term_day = lunar.next_solar_term(day)
        self.weekday.configure(text=WEEKDAY_LONG[day.weekday()])
        self.solar_day.configure(text=f"{day.day:02d}", text_color=RED if day.weekday() == 6 else TEXT)
        self.solar_month.configure(text=f"tháng {day.month}\nnăm {day.year}")
        self.lunar_day.configure(text=lunar.lunar_text(converted))
        length = "đủ" if lunar.lunar_month_length(day) == 30 else "thiếu"
        self.lunar_note.configure(text=f"Âm lịch, tháng {length}, năm con {lunar.year_zodiac(converted.year)}")
        names = (lunar.day_can_chi(day), lunar.month_can_chi(converted.month, converted.year), lunar.year_can_chi(converted.year))
        for label, name in zip(self.tiles, names):
            label.configure(text=name)
        self.spirit.configure(text=f"{'Hoàng đạo' if good else 'Hắc đạo'} · {spirit}", fg_color=GREEN_SOFT if good else RED_SOFT,
                              text_color=GREEN if good else RED)
        self.term.configure(text=f"Tiết {lunar.solar_term(day)}, tiếp theo là {next_term} ({term_day:%d/%m})")
        for label, hour in zip(self.hours, lunar.good_hours(day)):
            label.configure(text=f"{hour.name} {hour.start}–{hour.end}h")
        self.first_hour.configure(text=f"Giờ đầu ngày: {lunar.first_hour_can_chi(day)}")
        self.events.configure(text="\n".join(almanac.events_on(day)) or "Không có")
        self.saying.configure(text=almanac.daily_saying(day))
        self._show_tasks(tasks)

    def _show_tasks(self, tasks):
        signature = [(task["id"], task["title"], task["done_at"]) for task in tasks]
        if signature == self.task_signature:
            return
        self.task_signature = signature
        for child in self.task_rows.winfo_children():
            child.destroy()
        for task in tasks[:MAX_DAY_TASKS]:
            title = task["title"] if len(task["title"]) <= 40 else task["title"][:39] + "…"
            row = ctk.CTkLabel(self.task_rows, text=title, font=theme.text(13), text_color=MUTED if task["done_at"] else TEXT, anchor="w",
                               height=22, cursor="hand2")
            row.pack(fill="x")
            row.bind("<Button-1>", lambda _event, task_id=task["id"]: self.page.app.open_task(task_id))
        extra = f"+{len(tasks) - MAX_DAY_TASKS} việc nữa" if len(tasks) > MAX_DAY_TASKS else "" if tasks else "Chưa có việc nào"
        if extra:
            ctk.CTkLabel(self.task_rows, text=extra, font=theme.text(13), text_color=MUTED, anchor="w", height=22).pack(fill="x")


class FortuneView(ctk.CTkFrame):
    """Hỏi đáp tử vi. Có API key thì hỏi AI, chưa có thì luận mẫu ngay tại máy."""

    def __init__(self, master, page):
        super().__init__(master, fg_color="transparent")
        self.page = page
        self.store = page.store
        self.history = []
        self.question = ""
        self.answer = ""
        self.results = None
        self.stop_flag = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_chat()
        self._build_side()
        self._paint_tags()
        self._greet()
        AppearanceModeTracker.add(lambda _mode: self._paint_tags(), self)

    def _build_chat(self):
        card = Card(self)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)
        self.text = ctk.CTkTextbox(card, corner_radius=0, fg_color="transparent", text_color=TEXT, font=theme.text(14), wrap="word",
                                   activate_scrollbars=False, state="disabled", cursor="arrow", spacing3=4)
        self.text.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=(10, 4))
        scrollbar = ctk.CTkScrollbar(card, command=self.text.yview, width=12, fg_color="transparent", button_color=TRACK,
                                     button_hover_color=MUTED)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=10)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.suggestions = ctk.CTkFrame(card, fg_color="transparent")
        self.suggestions.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14)
        for question in ai.SUGGESTIONS:
            secondary_button(self.suggestions, question, lambda text=question: self.ask(text), anchor="w").pack(fill="x", pady=(0, 4))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(4, 12))
        self.send_button = primary_button(row, "Gửi", self._send_or_stop, width=68, height=38)
        self.send_button.pack(side="right", padx=(8, 0))
        self.entry = field(row, height=38, placeholder_text="Nhập câu hỏi tử vi của bạn…", font=theme.text(14))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda _: self.ask())

    def _build_side(self):
        side = Card(self, width=SIDE_WIDTH)
        side.grid(row=0, column=1, sticky="ns")
        side.pack_propagate(False)
        ctk.CTkLabel(side, text="Thỉnh thầy tử vi", font=theme.semibold(15), text_color=TEXT, anchor="w", height=24).pack(fill="x", padx=14, pady=(12, 0))
        self.status = self._note(side)
        self.status.pack(fill="x", padx=14)
        self._label(side, "Ngày xem")
        self.day_button = secondary_button(side, "", self._pick_day, anchor="w")
        self.day_button.pack(fill="x", padx=14)
        self._label(side, "Ngày sinh")
        self.birth = field(side, placeholder_text="dd/mm/yyyy")
        self.birth.pack(fill="x", padx=14)
        self.birth.bind("<Return>", self._save_birth)
        self.birth.bind("<FocusOut>", self._save_birth)
        self.birth_note = self._note(side)
        self.birth_note.pack(fill="x", padx=14, pady=(4, 0))
        stored = self._birth()
        if stored:
            set_text(self.birth, f"{stored:%d/%m/%Y}")
        self._show_birth(stored)
        secondary_button(side, "Cuộc trò chuyện mới", self.new_chat).pack(fill="x", padx=14, pady=(14, 0))
        privacy = self._note(side)
        privacy.configure(text="Khi có API key, câu hỏi cùng ngày sinh được gửi tới máy chủ AI đã cấu hình. Nội dung chỉ để tham khảo.",
                          font=theme.text(12))
        privacy.pack(side="bottom", fill="x", padx=14, pady=(0, 12))

    def _note(self, master):
        return ctk.CTkLabel(master, text="", font=theme.text(13), text_color=MUTED, anchor="w", justify="left", wraplength=SIDE_WIDTH - 30)

    def _label(self, master, title):
        ctk.CTkLabel(master, text=title, font=theme.semibold(13), text_color=TEXT, anchor="w", height=20).pack(fill="x", padx=14, pady=(12, 2))

    def _paint_tags(self):
        scale = ScalingTracker.get_widget_scaling(self)
        inner = self.text._textbox  # CTkTextbox không cho đặt font theo tag
        inner.tag_configure("label", foreground=resolve(ACCENT), font=(theme.FONT_SEMIBOLD, -round(12 * scale)), spacing1=round(10 * scale))
        inner.tag_configure("heading", foreground=resolve(TEXT), font=(theme.FONT_SEMIBOLD, -round(15 * scale)), spacing1=round(8 * scale))
        inner.tag_configure("bold", font=(theme.FONT_SEMIBOLD, -round(14 * scale)))
        inner.tag_configure("muted", foreground=resolve(MUTED))
        inner.tag_configure("error", foreground=resolve(RED))

    def _write(self, content, tag=None):
        self.text.configure(state="normal")
        self.text.insert("end", content, tag)
        self.text.configure(state="disabled")
        self.text.see("end")

    def _greet(self):
        self._write("Hãy hỏi thầy về ngày đang xem, hoặc chọn một câu gợi ý bên dưới.\n", "muted")

    def refresh(self, day):
        has_key = bool(self.store.setting("ai_key"))
        self.status.configure(text=f"Đang dùng {self.store.setting('ai_model')}" if has_key else "Chưa có API key, đang luận mẫu tại máy",
                              text_color=GREEN if has_key else MUTED)
        self.day_button.configure(text=f"{WEEKDAY_LONG[day.weekday()]}, {day:%d/%m/%Y}")

    def _pick_day(self):
        DatePicker(self.day_button, self.page.board.selected, self.page.select)

    def _birth(self):
        stored = self.store.setting("birth_date")
        return date.fromisoformat(stored) if stored else None

    def _show_birth(self, birth):
        self.birth_note.configure(text=f"Âm lịch: {ai.birth_lunar(birth)}" if birth else "Năm sinh được tính theo âm lịch")

    def _save_birth(self, _event=None):
        value = self.birth.get().strip()
        birth = parse_date(value)
        valid = birth is not None or not value
        self.birth.configure(border_color=BORDER if valid else RED)
        if valid:
            self.store.set_setting("birth_date", birth.isoformat() if birth else "")
            self._show_birth(birth)

    def new_chat(self):
        if self.results:
            self._stop()
        self.history = []
        self.answer = ""
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._greet()
        self.suggestions.grid()

    def _send_or_stop(self):
        if self.results:
            self._stop()
        else:
            self.ask()

    def _stop(self):
        self.stop_flag.set()
        self._finish()

    def ask(self, question=None):
        question = (question or self.entry.get()).strip()
        if not question or self.results:
            return "break"
        set_text(self.entry, "")
        self.suggestions.grid_remove()
        self.question = question
        self.answer = ""
        self._write("Bạn\n", "label")
        self._write(f"{question}\n")
        self._write("Tử vi AI\n", "label")
        self.text.mark_set("answer", "end-1c")
        self.text.mark_gravity("answer", "left")
        day, birth = self.page.board.selected, self._birth()
        key = self.store.secret("ai_key")
        if key:
            self._write("Đang luận giải…", "muted")
            self._start_stream(key, ai.build_messages(question, day, birth, self.history))
        else:
            self.answer = ai.offline_answer(question, day, birth)
            self._render_answer()
        return "break"

    def _start_stream(self, key, messages):
        self.results = queue.SimpleQueue()
        self.stop_flag = threading.Event()
        self.send_button.configure(text="Dừng")
        request = (self.store.setting("ai_url"), key, self.store.setting("ai_model"), messages)
        threading.Thread(target=self._stream, args=(request, self.results, self.stop_flag), daemon=True).start()
        self.after(POLL_MS, self._drain, self.results)

    @staticmethod
    def _stream(request, results, stop):
        from ..web import ApiError
        try:
            for piece in ai.stream_answer(*request):
                if stop.is_set():
                    return
                results.put(("text", piece))
            results.put(("done", ""))
        except ApiError as error:
            results.put(("error", str(error)))
        except Exception as error:  # luồng phụ chết im lặng sẽ để giao diện treo ở dòng "Đang luận giải"
            log("".join(traceback.format_exception(error)))
            results.put(("error", "Không đọc được phản hồi của máy chủ AI."))

    def _drain(self, results):
        if results is not self.results:
            return  # người dùng vừa bấm Dừng
        pieces, outcome = [], None
        while outcome is None and not results.empty():
            kind, content = results.get()
            if kind == "text":
                pieces.append(content)
            else:
                outcome = (kind, content)
        if pieces:
            self.answer += "".join(pieces)
            self._render_answer()
        if outcome:
            self._finish(outcome[1] if outcome[0] == "error" else "")
        else:
            self.after(POLL_MS, self._drain, results)

    def _render_answer(self):
        """Vẽ lại cả câu trả lời sau mỗi mảnh mới, vì dấu Markdown có thể đứt ngang giữa hai mảnh."""
        self.text.configure(state="normal")
        self.text.delete("answer", "end-1c")
        for content, style in ai.answer_runs(self.answer):
            self.text.insert("end", content, style)
        self.text.configure(state="disabled")
        self.text.see("end")

    def _finish(self, error=""):
        self.results = None
        self.send_button.configure(text="Gửi")
        if not self.answer:
            self.text.configure(state="normal")
            self.text.delete("answer", "end-1c")
            self.text.configure(state="disabled")
        if error:
            self._write(f"{error}\n", "error")
        elif self.answer:
            self.history += [{"role": "user", "content": self.question}, {"role": "assistant", "content": self.answer}]


class AlmanacPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=BG)
        self.app = app
        self.store = app.store
        self.quick = self  # Ctrl+N trên trang này thêm việc vào ngày đang chọn
        self.fortune = None
        self.popover = None
        self.today = date.today()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 8))
        self.tabs = segmented(header, list(TABS), self.set_tab, width=132, dynamic_resizing=False)
        self.tabs.pack(side="right")
        self.tabs.set(TABS[0])
        self.title_label = ctk.CTkLabel(header, text="", font=theme.display(25), text_color=TEXT, anchor="w", height=34)
        self.title_label.pack(side="left")
        self.controls = ctk.CTkFrame(header, fg_color="transparent")
        self.controls.pack(side="left")
        IconButton(self.controls, Icon.LEFT, lambda: self.step_month(-1), size=32, color=TEXT).pack(side="left", padx=(12, 0))
        IconButton(self.controls, Icon.RIGHT, lambda: self.step_month(1), size=32, color=TEXT).pack(side="left")
        secondary_button(self.controls, "Hôm nay", self.go_today, width=76).pack(side="left", padx=(6, 0))
        self.year_entry = field(self.controls, width=64, height=32, justify="center")
        self.year_entry.pack(side="left", padx=(6, 0))
        self.year_entry.bind("<Return>", self._go_year)
        self.year_entry.bind("<FocusOut>", self._go_year)

        view = ctk.CTkFrame(self, fg_color="transparent")
        view.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 20))
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(0, weight=1)
        self.calendar_view = view
        card = Card(view)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.board = MonthGrid(card, self)
        self.board.pack(fill="both", expand=True, padx=3, pady=3)
        self.events = EventList(view, self)
        self.events.grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(10, 0))
        self.panel = DayPanel(view, self)
        self.panel.grid(row=0, column=1, rowspan=2, sticky="ns")

    # ---------- Điều hướng ----------

    def set_tab(self, label):
        self.tabs.set(label)
        if label == TABS[1]:
            if self.fortune is None:
                self.fortune = FortuneView(self, self)
                self.fortune.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 20))
            self.calendar_view.grid_remove()
            self.fortune.grid()
            self.controls.pack_forget()
        else:
            if self.fortune is not None:
                self.fortune.grid_remove()
            self.calendar_view.grid()
            self.controls.pack(side="left")
        self.refresh(datetime.now())

    def select(self, day):
        day = min(max(day, date(MIN_YEAR, 1, 1)), date(MAX_YEAR, 12, 31))
        board = self.board
        board.selected = day
        board.year, board.month = day.year, day.month
        self.refresh(datetime.now())

    def step_month(self, direction):
        day = self.board.selected
        index = day.year * 12 + day.month - 1 + direction
        year, month = index // 12, index % 12 + 1
        if MIN_YEAR <= year <= MAX_YEAR:
            self.select(date(year, month, min(day.day, days_in_month(year, month))))

    def go_today(self):
        self.select(date.today())

    def _go_year(self, _event=None):
        value = self.year_entry.get().strip()
        if not (value.isdigit() and MIN_YEAR <= int(value) <= MAX_YEAR):
            set_text(self.year_entry, str(self.board.year))
            self.app.snackbar.show(f"Lịch hỗ trợ từ năm {MIN_YEAR} đến {MAX_YEAR}")
        elif int(value) != self.board.year:
            month = self.board.selected.month
            self.select(date(int(value), month, min(self.board.selected.day, days_in_month(int(value), month))))

    # ---------- Dữ liệu ----------

    def refresh(self, now):
        board = self.board
        if now.date() != self.today:
            if board.selected == self.today:  # qua ngày mới thì ngày đang chọn đi theo hôm nay
                board.selected = now.date()
                board.year, board.month = now.year, now.month
            self.today = now.date()
        days = month_days(board.year, board.month)
        first, last = days[0], days[-1] + timedelta(days=1)
        items = calendar_items(self.store.calendar_tasks(first, last), first, last)
        board.task_days = frozenset(item.start.date() for item in items)
        board.event_days = frozenset(day for day in days if almanac.events_on(day))
        board.schedule_draw()
        selected = {item.task["id"]: item.task for item in items if item.start.date() == board.selected}
        self.events.show(board.month, almanac.month_events(board.year, board.month))
        self.panel.show(board.selected, list(selected.values()))
        on_fortune = self.tabs.get() == TABS[1]
        self.title_label.configure(text="Tử vi" if on_fortune else f"Tháng {board.month}, {board.year}")
        if self.year_entry.focus_get() is not self.year_entry._entry:
            set_text(self.year_entry, str(board.year))
        if self.fortune is not None:
            self.fortune.refresh(board.selected)

    # ---------- Thêm việc ----------

    def focus_entry(self):
        self.add_task()

    def add_task(self):
        if self.popover is not None and self.popover.winfo_exists():
            self.popover.destroy()
        day = self.board.selected
        anchor = self.panel.add_button if self.panel.winfo_ismapped() else self.title_label
        position = (anchor.winfo_rootx() - 180, anchor.winfo_rooty() + anchor.winfo_height() + 4)
        self.popover = QuickPopover(self.board, *position, f"{WEEKDAY_SHORT[day.weekday()]} {day:%d/%m}",
                                    lambda content: add_on_day(self.app, content, day))
