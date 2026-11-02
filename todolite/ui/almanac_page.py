"""Trang Vạn niên: lịch tháng bên trái, tờ lịch của ngày đang chọn bên phải, và hỏi đáp tử vi.

Lưới tháng và tờ lịch đều vẽ trên Canvas như các trang lịch khác, nên đổi ngày bằng phím mũi tên
không phải dựng lại widget. Phần Tử vi chỉ dựng khi mở lần đầu, thư viện mạng chỉ nạp khi gọi AI.
"""
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
import traceback
from datetime import date, datetime, timedelta
from math import ceil

import customtkinter as ctk
from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import AppearanceModeTracker
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from .. import ai, almanac, daybook, lunar
from ..paths import log
from ..schedule import WEEKDAY_LONG, WEEKDAY_SHORT, calendar_items, days_in_month, from_text, month_days
from . import motion, theme
from .calendar import QuickPopover, add_on_day
from .theme import (ACCENT, AMBER, AMBER_SOFT, BG, BORDER, CARD, CARD_HOVER, FIELD, FILL, GREEN, GREEN_SOFT, Icon, MUTED, ON_FILL, RED, RED_SOFT,
                    TEXT, TRACK, blend, resolve)
from .shapes import rounded
from .textfit import fit_text
from .widgets import (Label, Card, DatePicker, FontCache, IconButton, Plain, field, measure_text, primary_button, secondary_button, segmented, set_text,
                      TextBox)

TABS = ("Lịch", "Tử vi")
MIN_YEAR, MAX_YEAR = 1800, 2199  # khoảng đã đối chiếu thuật toán lịch
LEFT_WIDTH, LEFT_WIDTH_NARROW, LEFT_BREAK = 410, 330, 980  # bề rộng cột lịch theo bề rộng phần nội dung
EVENTS_MIN_HEIGHT = 620  # thấp hơn mức này thì nhường chỗ cho lưới tháng
SIDE_WIDTH = 270
POLL_MS = 60
SOURCE_NOTE = ("Theo Ngọc Hạp Thông Thư, Hiệp Kỷ Biện Phương Thư và Việt Nam phong tục của Phan Kế Bính. Nội dung để tham khảo văn hoá: "
               "như sách đã viết, việc thành hay bại cốt do ở người.")


def parse_date(text):
    try:
        day = datetime.strptime(text.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None
    return day if MIN_YEAR <= day.year <= MAX_YEAR else None


class MonthGrid(tk.Canvas):
    """Lưới tháng dương kèm ngày âm. Dưới cùng là chú giải các dấu trên ô."""
    HEAD, LEGEND = 28, 26
    FONTS = {"head": ("FONT_SEMIBOLD", 12, 0), "solar": ("FONT_SEMIBOLD", 16, 0), "lunar": ("FONT_TEXT", 11, 0), "dot": ("FONT_ICON", 7, 0),
             "legend": ("FONT_TEXT", 12, 0)}
    LEGEND_ITEMS = (("good", "Ngày tốt"), ("bad", "Ngày xấu"), ("task", "Có việc"), ("event", "Ngày lễ"))

    def __init__(self, master, page):
        super().__init__(master, highlightthickness=0, bd=0, bg=resolve(CARD), takefocus=1, cursor="hand2")
        self.page = page
        self.selected = date.today()
        self.year, self.month = self.selected.year, self.selected.month
        self.event_days = self.task_days = frozenset()
        self.quality = {}
        self.hover = None
        self.layout = (0, 1, 1, ())
        self.scale = 1.0
        self.fonts = FontCache(self.FONTS)
        self.draw_pending = False

        self.bind("<Configure>", lambda _: self.schedule_draw())
        self.bind("<Motion>", lambda event: self._set_hover(self._day_at(event.x, event.y)))
        self.bind("<Leave>", lambda _: self._set_hover(None))
        self.bind("<Button-1>", self._on_click)
        motion.Stepper(self, self.page.step_month)  # bàn di chuột: mỗi lần vuốt lật đúng một tháng
        for key, days in (("<Left>", -1), ("<Right>", 1), ("<Up>", -7), ("<Down>", 7)):
            self.bind(key, lambda _event, step=days: self.page.select(self.selected + timedelta(days=step)))
        self.bind("<Prior>", lambda _: self.page.step_month(-1))
        self.bind("<Next>", lambda _: self.page.step_month(1))
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
        head, legend = round(self.HEAD * self.scale), round(self.LEGEND * self.scale)
        cell_w, cell_h = width / 7, (height - head - legend) / (len(days) // 7)
        self.layout = (head, cell_w, cell_h, days)
        colors = {name: resolve(pair) for name, pair in (("card", CARD), ("hover", CARD_HOVER), ("border", BORDER), ("text", TEXT),
                                                         ("muted", MUTED), ("accent", ACCENT), ("fill", FILL), ("on_fill", ON_FILL),
                                                         ("red", RED), ("amber", AMBER), ("green", GREEN))}
        for column, name in enumerate(WEEKDAY_SHORT):
            self.create_text((column + 0.5) * cell_w, head / 2, text=name, font=self.fonts.get("head"),
                             fill=colors["red" if column == 6 else "muted"])
        today = date.today()
        for index, day in enumerate(days):
            self._paint_cell(day, index % 7 * cell_w, head + index // 7 * cell_h, cell_w, cell_h, colors, today)
        self._paint_legend(height - legend / 2, colors)

    def _mark(self, kind, x, y, colors):
        """Dấu trên ô lịch. Ngày xấu là tam giác để phân biệt được cả khi không nhận ra màu."""
        size = round(4 * self.scale)
        if kind == "bad":
            self.create_polygon(x, y - size, x + size, y + size - 1, x - size, y + size - 1, outline="", fill=colors["red"])
        else:
            color = {"good": "green", "task": "accent", "event": "amber"}[kind]
            self.create_text(x, y, text=Icon.DOT, font=self.fonts.get("dot"), fill=colors[color])

    def _paint_legend(self, y, colors):
        x = round(10 * self.scale)
        for kind, label in self.LEGEND_ITEMS:
            self._mark(kind, x, y, colors)
            x += round(9 * self.scale)
            self.create_text(x, y, text=label, anchor="w", font=self.fonts.get("legend"), fill=colors["muted"])
            x += self.fonts.measure("legend", label) + round(16 * self.scale)

    def _paint_cell(self, day, x, y, width, height, colors, today):
        inset = round(2 * self.scale)
        box = (x + inset, y + inset, x + width - inset, y + height - inset)
        radius = round(theme.RADIUS_CONTROL * self.scale)
        back = colors["card"]
        if day == self.selected:
            back = blend(colors["fill"], colors["card"], 0.16)
            rounded(self, *box, radius, back, colors["card"], outline=colors["accent"])
        elif day == self.hover:
            back = colors["hover"]
            rounded(self, *box, radius, back, colors["card"])
        middle = x + width / 2
        number_y = y + height * 0.38
        half = self.fonts.measure("solar", str(day.day)) / 2  # các dấu đứng sát con số, không rời ra góc ô
        if day == today:
            half = round(13 * self.scale)
            rounded(self, middle - half, number_y - half, middle + half, number_y + half, half, colors["fill"], back)
            color = colors["on_fill"]
        elif day.month != self.month:
            color = colors["muted"]
        else:
            color = colors["red" if day.weekday() == 6 else "text"]
        self.create_text(middle, number_y, text=str(day.day), font=self.fonts.get("solar"), fill=color)
        label = lunar.lunar_label(day)
        lunar_y = y + height * 0.74
        self.create_text(middle, lunar_y, text=label, font=self.fonts.get("lunar"), fill=colors["accent" if "/" in label else "muted"])
        gap = round(5 * self.scale)
        quality = self.quality.get(day, daybook.AVERAGE)
        if quality != daybook.AVERAGE and day.month == self.month:
            self._mark("good" if quality == daybook.GOOD else "bad", middle - self.fonts.measure("lunar", label) / 2 - gap - round(2 * self.scale), lunar_y, colors)
        if day in self.event_days:
            self._mark("event", middle + half + gap, number_y - round(8 * self.scale), colors)
        if day in self.task_days:
            self._mark("task", middle - half - gap, number_y - round(8 * self.scale), colors)

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
    """Các ngày lễ trong tháng, bấm một dòng để tới ngày đó. Ô chữ cao vừa khít số dòng, không lộ nửa dòng cuối."""
    ROWS, TAB = 4, 52

    def __init__(self, master, page):
        super().__init__(master)
        self.page = page
        self.signature = None
        self.title = Label(self, text="", font=theme.semibold(14), text_color=TEXT, anchor="w", height=22)
        self.title.pack(fill="x", padx=14, pady=(8, 0))
        self.text = TextBox(self, height=84, corner_radius=0, fg_color="transparent", text_color=TEXT, font=theme.text(13),
                            wrap="none", cursor="arrow", state="disabled", takefocus=0)
        self.text.pack(fill="x", padx=(10, 4), pady=(0, 6))
        self._paint_tags()
        AppearanceModeTracker.add(lambda _mode: self._paint_tags(), self)
        ScalingTracker.add_widget(self._on_scaling, self)
        self._on_scaling(ScalingTracker.get_widget_scaling(self))
        self.text.bind("<Configure>", lambda _: self._render())

    def _on_scaling(self, scale, _window=None):
        line = tkfont.Font(family=theme.FONT_TEXT, size=-round(13 * scale)).metrics("linespace")
        self.text.configure(height=ceil(self.ROWS * line / scale) + 8, tabs=(round(self.TAB * scale),))

    def _paint_tags(self):
        self.text.tag_config("date", foreground=resolve(ACCENT))
        self.text.tag_config("muted", foreground=resolve(MUTED))

    def show(self, month, events):
        if (month, events) != self.signature:
            self.signature = (month, events)
            self.title.configure(text=f"Sự kiện tháng {month}")
            self._render()

    def _render(self):
        if self.signature is None:
            return
        month, events = self.signature
        scale = ScalingTracker.get_widget_scaling(self)
        room = self.text.winfo_width() - round((self.TAB + 12) * scale)
        measure = lambda piece: measure_text(theme.text(13), scale, piece)  # noqa: E731
        text = self.text
        text.configure(state="normal")
        text.delete("1.0", "end")
        if not events:
            text.insert("end", f"Không có sự kiện nổi bật trong tháng {month}.", "muted")
        for index, (day, name) in enumerate(events):
            tag = f"event{index}"
            text.insert("end", f"{day:%d/%m}", ("date", tag))
            label = fit_text(measure, name, room) if room > 0 else name
            text.insert("end", f"\t{label}\n", tag)
            text.tag_bind(tag, "<Button-1>", lambda _event, target=day: self.page.select(target))
        text.configure(state="disabled")


class Converter(Card):
    """Đổi ngày âm sang dương rồi nhảy tới ngày đó."""

    def __init__(self, master, page):
        super().__init__(master)
        self.page = page
        Label(self, text="Đổi ngày âm sang dương", font=theme.semibold(14), text_color=TEXT, anchor="w", height=22).pack(
            fill="x", padx=14, pady=(8, 2))
        row = Plain(self)
        row.pack(fill="x", padx=14)
        self.fields = [field(row, width=width, height=30, justify="center", placeholder_text=hint) for hint, width in (("Ngày", 54), ("Tháng", 62), ("Năm", 54))]
        for entry in self.fields:
            entry.pack(side="left", padx=(0, 4))
            entry.bind("<Return>", lambda _: self.convert())
        self.leap = ctk.CTkCheckBox(row, text="Nhuận", width=64, font=theme.text(13), text_color=TEXT, checkbox_width=18, checkbox_height=18,
                                    corner_radius=theme.RADIUS_CHIP, border_width=1, border_color=MUTED, fg_color=FILL, hover_color=theme.FILL_HOVER)
        self.leap.pack(side="left", padx=(2, 0))
        secondary_button(row, "Đổi", self.convert, width=44, height=30).pack(side="right")
        self.result = Label(self, text="", font=theme.text(13), text_color=MUTED, anchor="w", height=20)
        self.result.pack(fill="x", padx=14, pady=(0, 6))

    def convert(self):
        try:
            day, month, year = (int(entry.get()) for entry in self.fields)
        except ValueError:
            self.result.configure(text="Hãy nhập đủ ngày, tháng và năm âm lịch", text_color=RED)
            return
        solar = lunar.lunar_to_solar(day, month, year, self.leap.get() == 1) if MIN_YEAR <= year <= MAX_YEAR else None
        if solar is None:
            self.result.configure(text="Không có ngày âm này", text_color=RED)
            return
        self.page.select(solar)
        self.result.configure(text=f"{WEEKDAY_LONG[solar.weekday()]}, {solar:%d/%m/%Y}", text_color=ACCENT)


class DaySheet(Card):
    """Tờ lịch của ngày đang chọn, xếp theo thứ tự người xem cần: tốt hay xấu, hạn gì, nên gì, kiêng gì, rồi tới chi tiết."""
    PAD, GAP, RADIUS = 15, 18, theme.RADIUS_CONTROL
    COLUMNS_FROM = 460  # từ bề rộng này, các khối đôi đứng cạnh nhau
    KEY_WIDTH = 112
    FONTS = {"date": ("FONT_DISPLAY", 72, 0), "lunar": ("FONT_DISPLAY", 32, 0), "title": ("FONT_SEMIBOLD", 16, 0), "body": ("FONT_TEXT", 14, 0),
             "strong": ("FONT_SEMIBOLD", 14, 0), "small": ("FONT_TEXT", 13, 0), "label": ("FONT_SEMIBOLD", 13, 0), "note": ("FONT_TEXT", 12, 0),
             "glyph": ("FONT_ICON", 16, 0), "mini": ("FONT_ICON", 12, 0)}

    def __init__(self, master, page):
        super().__init__(master)
        self.page = page
        self.day = None
        self.tasks = []
        self.birth = None
        self.fonts = FontCache(self.FONTS)
        self.scale = 1.0
        self.colors = {}
        self.draw_pending = False
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=resolve(CARD))
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(5, 0), pady=5)  # chừa góc bo của thẻ, Canvas không tự bo được
        self.scroller = motion.canvas_scroller(self.canvas)
        self.scrollbar = motion.ScrollStrip(self, CARD).attach(self.scroller, self.canvas)
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 2), pady=8)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.bind("<Configure>", lambda _: self.schedule_draw())
        AppearanceModeTracker.add(lambda _mode: self._on_theme(), self)

    def _on_theme(self):
        self.canvas.configure(bg=resolve(CARD))
        self.schedule_draw()

    def show(self, day, tasks, birth):
        changed = day != self.day
        self.day, self.tasks, self.birth = day, tasks, birth
        self.schedule_draw()
        if changed:
            self.scroller.halt()
            self.canvas.yview_moveto(0)

    def schedule_draw(self):
        if not self.draw_pending:
            self.draw_pending = True
            self.after_idle(self._paint)

    def _size(self, value):
        return round(value * self.scale)

    def _text(self, x, y, content, font, color, width=None, anchor="nw", justify="left"):
        """Vẽ một đoạn chữ, trả về toạ độ đáy để khối sau đặt tiếp."""
        options = {"width": width} if width else {}
        item = self.canvas.create_text(x, y, text=content, anchor=anchor, justify=justify, font=self.fonts.get(font), fill=self.colors[color], **options)
        return self.canvas.bbox(item)[3]

    def _paint(self):
        self.draw_pending = False
        if not self.winfo_exists() or self.day is None:
            return
        canvas = self.canvas
        canvas.delete("all")
        self.scale = ScalingTracker.get_widget_scaling(self)
        self.fonts.rescale(self.scale)
        width = canvas.winfo_width()
        if width < 120:
            return
        self.colors = {name: resolve(pair) for name, pair in (
            ("card", CARD), ("hover", CARD_HOVER), ("border", BORDER), ("text", TEXT), ("muted", MUTED), ("accent", ACCENT), ("red", RED), ("green", GREEN),
            ("amber", AMBER), ("green_soft", GREEN_SOFT), ("red_soft", RED_SOFT), ("amber_soft", AMBER_SOFT), ("field", FIELD), ("fill", FILL), ("on_fill", ON_FILL))}
        self.x0, self.x1 = self._size(self.PAD), width - self._size(self.PAD)
        self.wide = self.x1 - self.x0 >= self._size(self.COLUMNS_FROM)
        reading = daybook.read_day(self.day)
        y = self._header(self._size(14))
        y = self._verdict(y + self._size(12), reading)
        y = self._hardships(y, reading)
        y = self._advice(y, reading)
        y = self._hours(y)
        y = self._ages(y, reading)
        y = self._details(y, reading)
        y = self._stars(y, reading)
        y = self._own_tasks(y)
        y = self._sayings(y)
        y = self._text(self.x0, y + self._size(self.GAP), SOURCE_NOTE, "note", "muted", self.x1 - self.x0)
        canvas.configure(scrollregion=(0, 0, width, y + self._size(self.PAD)))

    # ---------- Đầu tờ lịch ----------

    def _header(self, y):
        day, canvas = self.day, self.canvas
        converted = lunar.solar_to_lunar(day)
        color = "red" if day.weekday() == 6 else "text"
        number = canvas.create_text(self.x0, y, text=f"{day.day:02d}", anchor="nw", font=self.fonts.get("date"), fill=self.colors[color])
        left, top, right, bottom = canvas.bbox(number)
        middle = top + (bottom - top) * 0.28
        left_x = right + self._size(12)
        self._text(left_x, middle, WEEKDAY_LONG[day.weekday()], "title", color)
        solar_month = f"Tháng {day.month}, {day.year}"
        self._text(left_x, middle + self._size(24), solar_month, "small", "muted")
        lunar_top = top + self._size(6)
        self._text(self.x1, lunar_top, str(converted.day), "lunar", "accent", anchor="ne")
        month = f"tháng {converted.month}{' nhuận' if converted.leap else ''} âm lịch"
        room = self.x1 - left_x - self.fonts.measure("small", solar_month) - self._size(16)  # hẹp thì xuống dòng, không đè lên tháng dương
        self._text(self.x1, lunar_top + self._size(44), month, "small", "muted", room, "ne", "right")
        y = self._text(self.x0, bottom + self._size(2),
                       f"Ngày {lunar.day_can_chi(day)} · Tháng {lunar.month_can_chi(converted.month, converted.year)} · Năm {lunar.year_can_chi(converted.year)}",
                       "strong", "text", self.x1 - self.x0)
        for name in almanac.events_on(day):
            y = self._text(self.x0, y + self._size(2), name, "strong", "accent", self.x1 - self.x0)
        next_term, term_day = lunar.next_solar_term(day)
        length = "đủ" if lunar.lunar_month_length(day) == 30 else "thiếu"
        return self._text(self.x0, y + self._size(2),
                          f"Tiết {lunar.solar_term(day)}, tiếp theo {next_term} ({term_day:%d/%m}) · Tháng {length} · Năm con {lunar.year_zodiac(converted.year)}",
                          "small", "muted", self.x1 - self.x0)

    def _verdict(self, y, reading):
        fill, color, glyph = {daybook.GOOD: ("green_soft", "green", Icon.DONE), daybook.AVERAGE: ("amber_soft", "amber", Icon.RING),
                              daybook.BAD: ("red_soft", "red", Icon.WARNING)}[reading.quality]
        pad = self._size(12)
        canvas = self.canvas
        text_x = self.x0 + pad + self._size(28)
        room = self.x1 - pad - text_x
        title_bottom = self._text(text_x, y + pad - self._size(2), reading.title, "title", color)
        bottom = self._text(text_x, title_bottom + self._size(1), reading.reason[0].upper() + reading.reason[1:], "small", "text", room) + pad - self._size(2)
        canvas.create_text(self.x0 + pad + self._size(10), y + pad + self._size(9), text=glyph, font=self.fonts.get("glyph"), fill=self.colors[color])
        panel = rounded(canvas, self.x0, y, self.x1, bottom, self._size(self.RADIUS), self.colors[fill], self.colors["card"])
        canvas.tag_lower(panel)
        return bottom

    def _heading(self, y, title, detail=""):
        y += self._size(self.GAP)
        self.canvas.create_line(self.x0, y, self.x1, y, fill=self.colors["border"])
        y += self._size(12)
        bottom = self._text(self.x0, y, title, "title", "text")
        if detail:
            self._text(self.x1, y + self._size(3), detail, "small", "muted", anchor="ne")
        return bottom + self._size(6)

    # ---------- Hạn, nên làm, kiêng kỵ ----------

    def _hardships(self, y, reading):
        personal = daybook.age_note(self.day, self.birth) if self.birth else None
        marks = reading.marks
        y = self._heading(y, "Hạn trong ngày")
        if not marks:
            y = self._text(self.x0, y, "Không phạm Tam Nương, Nguyệt Kỵ, Nguyệt Tận, Dương Công, Sát Chủ, Thụ Tử hay Trùng Tang.", "small", "muted", self.x1 - self.x0) + self._size(2)
        for mark in marks:
            y = self._mark_row(y, mark)
        if personal and not personal[0]:
            y = self._mark_row(y, daybook.Mark("Tuổi của bạn", daybook.MINOR, personal[1], ()))
        return y

    def _mark_row(self, y, mark):
        label, fill, color = {daybook.MAJOR: ("Đại kỵ", "red", "card"), daybook.MINOR: ("Kỵ", "amber_soft", "amber"),
                              daybook.SPECIFIC: ("Kiêng riêng", "field", "muted")}[mark.level]
        chip_w = self._size(76)
        chip_h = self._size(20)
        rounded(self.canvas, self.x0, y + self._size(1), self.x0 + chip_w, y + self._size(1) + chip_h, self._size(theme.RADIUS_CHIP), self.colors[fill], self.colors["card"])
        self.canvas.create_text(self.x0 + chip_w / 2, y + self._size(1) + chip_h / 2, text=label, font=self.fonts.get("note"), fill=self.colors[color])
        x = self.x0 + chip_w + self._size(10)
        bottom = self._text(x, y, mark.name, "strong", "text")
        return self._text(x, bottom, mark.note, "small", "muted", self.x1 - x) + self._size(8)

    def _advice(self, y, reading):
        y += self._size(self.GAP - 6)
        gap = self._size(10)
        if self.wide:
            middle = (self.x0 + self.x1) / 2
            left = self._advice_panel(self.x0, y, middle - gap / 2, "Nên làm", Icon.DONE, "green", "green_soft", reading.do, self._nothing_to_start(reading))
            right = self._advice_panel(middle + gap / 2, y, self.x1, "Kiêng kỵ", Icon.CLOSE, "red", "red_soft", reading.avoid, "Không có việc phải kiêng riêng")
            return self._match_panels(left, right)
        first = self._advice_panel(self.x0, y, self.x1, "Nên làm", Icon.DONE, "green", "green_soft", reading.do, self._nothing_to_start(reading))
        second = self._advice_panel(self.x0, first[4] + gap, self.x1, "Kiêng kỵ", Icon.CLOSE, "red", "red_soft", reading.avoid, "Không có việc phải kiêng riêng")
        return second[4]

    @staticmethod
    def _nothing_to_start(reading):
        return "Không có việc nên khởi sự, chỉ làm việc thường ngày" if reading.avoid else "Ngày này không có việc nào đặc biệt hợp"

    def _advice_panel(self, x0, y, x1, title, glyph, color, fill, items, empty):
        pad = self._size(12)
        x, room = x0 + pad, x1 - x0 - 2 * pad
        self.canvas.create_text(x, y + pad, text=glyph, anchor="nw", font=self.fonts.get("mini"), fill=self.colors[color])
        bottom = self._text(x + self._size(20), y + pad - self._size(3), title, "title", color) + self._size(4)
        if not items:
            bottom = self._text(x, bottom, empty, "small", "muted", room) + self._size(4)
        for item in items:
            bottom = self._text(x, bottom, item.task, "strong", "text", room)
            if item.reasons:
                bottom = self._text(x, bottom, ", ".join(item.reasons[:3]), "note", "muted", room)
            bottom += self._size(5)
        bottom += pad - self._size(5)
        panel = rounded(self.canvas, x0, y, x1, bottom, self._size(self.RADIUS), self.colors[fill], self.colors["card"])
        self.canvas.tag_lower(panel)
        return panel, x0, x1, y, bottom, fill

    def _match_panels(self, left, right):
        """Hai khối đứng cạnh nhau phải cao bằng nhau."""
        bottom = max(left[4], right[4])
        for panel, x0, x1, top, end, fill in (left, right):
            if end != bottom:
                self.canvas.delete(panel)
                self.canvas.tag_lower(rounded(self.canvas, x0, top, x1, bottom, self._size(self.RADIUS), self.colors[fill], self.colors["card"]))
        return bottom

    # ---------- Giờ, tuổi, chi tiết ----------

    def _hours(self, y):
        y = self._heading(y, "Giờ trong ngày", "Ô xanh là giờ hoàng đạo")
        slots = daybook.hours_of(self.day)
        now = datetime.now()
        columns = 12 if self.x1 - self.x0 >= self._size(12 * 44) else 6
        cell_w = (self.x1 - self.x0) / columns
        cell_h = self._size(44)
        for index, slot in enumerate(slots):
            x = self.x0 + index % columns * cell_w
            top = y + index // columns * cell_h
            fill = "green_soft" if slot.good else "field"
            color = "green" if slot.good else "muted"
            current = self.day == now.date() and (now.hour - slot.start) % 24 < 2
            rounded(self.canvas, x + 1, top + 1, x + cell_w - 1, top + cell_h - 2, self._size(theme.RADIUS_CONTROL), self.colors[fill], self.colors["card"],
                    outline=self.colors["accent"] if current else "", width=self._size(2))
            self.canvas.create_text(x + cell_w / 2, top + cell_h * 0.32, text=slot.name, font=self.fonts.get("label"), fill=self.colors[color])
            self.canvas.create_text(x + cell_w / 2, top + cell_h * 0.68, text=f"{slot.start}–{slot.end}", font=self.fonts.get("note"), fill=self.colors[color])
        bottom = y + (12 // columns) * cell_h
        good = ", ".join(f"{slot.name} ({slot.spirit})" for slot in slots if slot.good)
        return self._text(self.x0, bottom + self._size(4), f"Giờ tốt: {good}. Giờ Tý đầu ngày là {lunar.first_hour_can_chi(self.day)}.", "note", "muted", self.x1 - self.x0)

    def _row(self, y, key, value, color="text"):
        self._text(self.x0, y + self._size(1), key, "small", "muted")
        x = self.x0 + self._size(self.KEY_WIDTH)
        return self._text(x, y, value, "body", color, self.x1 - x) + self._size(5)

    def _ages(self, y, reading):
        y = self._heading(y, "Tuổi và hướng")
        y = self._row(y, "Kỵ tuổi", ", ".join(reading.clashes), "red")
        y = self._row(y, "Xung", f"Tuổi {reading.conflict}")
        y = self._row(y, "Hợp", "Tuổi " + ", ".join(reading.harmony), "green")
        personal = daybook.age_note(self.day, self.birth) if self.birth else None
        if personal and personal[0]:
            y = self._row(y, "Tuổi của bạn", personal[1], "green")
        joy, wealth, crane = reading.directions
        y = self._row(y, "Hướng tốt", f"Hỷ Thần {joy}, Tài Thần {wealth}", "green")
        if crane:
            y = self._row(y, "Hướng xấu", f"Hạc Thần {crane}", "red")
        travel = reading.travel
        return self._row(y, "Xuất hành", f"Ngày {travel.name}: {travel.note}", "green" if travel.good else "red")

    def _details(self, y, reading):
        y = self._heading(y, "Luận ngày")
        truc, mansion = reading.truc, reading.mansion
        y = self._row(y, "Thần trực", f"{reading.spirit}, {'hoàng đạo' if reading.spirit_good else 'hắc đạo'}", "green" if reading.spirit_good else "red")
        y = self._row(y, "Trực", f"{truc.name}: {truc.note}")
        y = self._row(y, "Nhị thập bát tú", f"{mansion.name}, tướng tinh con {mansion.animal}, {'sao tốt' if mansion.good else 'sao xấu'}")
        y = self._row(y, "Ngũ hành", f"{reading.element}. {reading.element_note}")
        return self._row(y, "Bành Tổ", ". ".join(reading.taboos))

    def _stars(self, y, reading):
        y = self._heading(y, "Sao trong ngày", f"{len(reading.good_stars)} tốt, {len(reading.bad_stars)} xấu")
        if self.wide:
            middle = (self.x0 + self.x1) / 2
            room = (self.x1 - self.x0 - self._size(16)) / 2
            left = self._star_list(self.x0, y, room, "Sao tốt", "green", reading.good_stars)
            return max(left, self._star_list(middle + self._size(8), y, room, "Sao xấu", "red", reading.bad_stars))
        y = self._star_list(self.x0, y, self.x1 - self.x0, "Sao tốt", "green", reading.good_stars)
        return self._star_list(self.x0, y + self._size(8), self.x1 - self.x0, "Sao xấu", "red", reading.bad_stars)

    def _star_list(self, x, y, room, title, color, stars):
        bottom = self._text(x, y, title, "label", color) + self._size(2)
        if not stars:
            return self._text(x, bottom, "Không có", "small", "muted")
        for star in stars:
            bottom = self._text(x, bottom, star.name, "label", "text", room)
            bottom = self._text(x, bottom, star.note, "note", "muted", room) + self._size(4)
        return bottom

    # ---------- Việc riêng và câu của ngày ----------

    def _own_tasks(self, y):
        y = self._heading(y, "Việc trong ngày", f"{len(self.tasks)} việc" if self.tasks else "")
        if not self.tasks:
            return self._text(self.x0, y, "Chưa có việc nào. Bấm Thêm việc ở trên để ghi vào ngày này.", "small", "muted", self.x1 - self.x0)
        for task in sorted(self.tasks, key=lambda item: (bool(item["done_at"]), not item["all_day"], item["due_at"] or "")):
            y = self._task_row(y, task)
        return y

    def _task_row(self, y, task):
        done = bool(task["done_at"])
        canvas = self.canvas
        tag = f"task{task['id']}"
        due = "Đã xong" if done else from_text(task["due_at"]).strftime("%H:%M") if task["due_at"] and not task["all_day"] else "Cả ngày"
        item = canvas.create_text(self.x0, y, text=due, anchor="nw", font=self.fonts.get("small"), fill=self.colors["muted"], tags=tag)
        title = canvas.create_text(self.x0 + self._size(62), y, text=self.fonts.fit("body", task["title"], self.x1 - self.x0 - self._size(62)), anchor="nw",
                                   font=self.fonts.get("body"), fill=self.colors["muted" if done else "text"], tags=tag)
        canvas.tag_bind(tag, "<Button-1>", lambda _event, task_id=task["id"]: self.page.app.open_task(task_id))
        canvas.tag_bind(tag, "<Enter>", lambda _event: canvas.configure(cursor="hand2"))
        canvas.tag_bind(tag, "<Leave>", lambda _event: canvas.configure(cursor=""))
        return max(canvas.bbox(item)[3], canvas.bbox(title)[3]) + self._size(4)

    def _sayings(self, y):
        y = self._heading(y, "Câu của ngày")
        for saying in almanac.daily_sayings(self.day):
            y = self._text(self.x0, y, saying.kind, "label", "accent") + self._size(1)
            y = self._text(self.x0, y, saying.text, "strong", "text", self.x1 - self.x0)
            if saying.meaning:
                y = self._text(self.x0, y, f"Nghĩa: {saying.meaning}", "small", "muted", self.x1 - self.x0)
            y = self._text(self.x0, y, saying.source, "note", "muted", self.x1 - self.x0) + self._size(8)
        return y


class FortuneView(Plain):
    """Hỏi đáp tử vi. Có API key thì hỏi AI, chưa có thì luận mẫu ngay tại máy."""

    def __init__(self, master, page):
        super().__init__(master)
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
        ScalingTracker.add_widget(lambda *_: self._paint_tags(), self)

    def _build_chat(self):
        card = Card(self)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)
        self.text = TextBox(card, corner_radius=0, fg_color="transparent", text_color=TEXT, font=theme.text(14), wrap="word",
                            state="disabled", cursor="arrow", spacing3=4)
        self.text.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=(10, 4))
        self.scroller = motion.text_scroller(self.text._textbox)
        scrollbar = motion.ScrollStrip(card, CARD).attach(self.scroller, self.text._textbox)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=10)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.suggestions = Plain(card)
        self.suggestions.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14)
        for question in ai.SUGGESTIONS:
            secondary_button(self.suggestions, question, lambda text=question: self.ask(text), anchor="w").pack(fill="x", pady=(0, 4))
        row = Plain(card)
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
        Label(side, text="Thỉnh thầy tử vi", font=theme.semibold(16), text_color=TEXT, anchor="w", height=26).pack(fill="x", padx=14, pady=(12, 0))
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
        return Label(master, text="", font=theme.text(13), text_color=MUTED, anchor="w", justify="left", wraplength=SIDE_WIDTH - 30)

    def _label(self, master, title):
        Label(master, text=title, font=theme.semibold(13), text_color=TEXT, anchor="w", height=20).pack(fill="x", padx=14, pady=(12, 2))

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

        header = Plain(self)
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 8))
        self.tabs = segmented(header, list(TABS), self.set_tab, width=132, dynamic_resizing=False)
        self.tabs.pack(side="right")
        self.tabs.set(TABS[0])
        self.shown_tab = TABS[0]
        self.add_button = primary_button(header, "Thêm việc", self.add_task, width=92)
        self.add_button.pack(side="right", padx=(0, 10))
        self.title_label = Label(header, text="", font=theme.display(24), text_color=TEXT, anchor="w", height=36)
        self.title_label.pack(side="left")
        self.controls = Plain(header)
        self.controls.pack(side="left")
        IconButton(self.controls, Icon.LEFT, lambda: self.step_month(-1), size=32, color=TEXT).pack(side="left", padx=(12, 0))
        IconButton(self.controls, Icon.RIGHT, lambda: self.step_month(1), size=32, color=TEXT).pack(side="left")
        secondary_button(self.controls, "Hôm nay", self.go_today, width=76).pack(side="left", padx=(6, 0))
        self.year_entry = field(self.controls, width=64, height=32, justify="center")
        self.year_entry.pack(side="left", padx=(6, 0))
        self.year_entry.bind("<Return>", self._go_year)
        self.year_entry.bind("<FocusOut>", self._go_year)

        view = Plain(self)
        view.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 20))
        view.grid_columnconfigure(1, weight=1)
        view.grid_rowconfigure(0, weight=1)
        view.bind("<Configure>", self._fit_columns)
        self.calendar_view = view
        self.left = Plain(view, width=LEFT_WIDTH)
        self.left.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        self.left.pack_propagate(False)
        card = Card(self.left)
        card.pack(fill="both", expand=True)
        self.board = MonthGrid(card, self)
        self.board.pack(fill="both", expand=True, padx=5, pady=5)  # chừa góc bo của thẻ
        self.events = EventList(self.left, self)
        self.events.pack(fill="x", pady=(10, 0))
        self.converter = Converter(self.left, self)
        self.converter.pack(fill="x", pady=(10, 0))
        self.events_shown = True
        self.sheet = DaySheet(view, self)
        self.sheet.grid(row=0, column=1, sticky="nsew")

    def _fit_columns(self, event):
        """Cột lịch hẹp lại khi cửa sổ nhỏ để tờ lịch còn đủ chỗ đọc, cửa sổ thấp thì ẩn danh sách sự kiện."""
        scale = ScalingTracker.get_widget_scaling(self)
        wanted = LEFT_WIDTH if event.width / scale >= LEFT_BREAK else LEFT_WIDTH_NARROW
        if self.left.cget("width") != wanted:
            self.left.configure(width=wanted)
        shown = event.height / scale >= EVENTS_MIN_HEIGHT
        if shown != self.events_shown:
            self.events_shown = shown
            if shown:
                self.events.pack(fill="x", pady=(10, 0), before=self.converter)
            else:
                self.events.pack_forget()

    # ---------- Điều hướng ----------

    def set_tab(self, label):
        with self.app.fade(when=label != self.shown_tab):
            self._set_tab(label)

    def _set_tab(self, label):
        self.shown_tab = label
        self.tabs.set(label)
        if label == TABS[1]:
            if self.fortune is None:
                self.fortune = FortuneView(self, self)
                self.fortune.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 20))
            self.calendar_view.grid_remove()
            self.fortune.grid()
            self.controls.pack_forget()
            self.add_button.pack_forget()
        else:
            if self.fortune is not None:
                self.fortune.grid_remove()
            self.calendar_view.grid()
            self.controls.pack(side="left")
            self.add_button.pack(side="right", padx=(0, 10))
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
        board.quality = {day: daybook.quality_of(day) for day in days}
        board.schedule_draw()
        selected = {item.task["id"]: item.task for item in items if item.start.date() == board.selected}
        self.events.show(board.month, almanac.month_events(board.year, board.month))
        stored = self.store.setting("birth_date")
        self.sheet.show(board.selected, list(selected.values()), date.fromisoformat(stored) if stored else None)
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
        anchor = self.add_button if self.add_button.winfo_ismapped() else self.title_label
        position = (anchor.winfo_rootx() - 180, anchor.winfo_rooty() + anchor.winfo_height() + 4)
        self.popover = QuickPopover(self.board, *position, f"{WEEKDAY_SHORT[day.weekday()]} {day:%d/%m}",
                                    lambda content: add_on_day(self.app, content, day))
