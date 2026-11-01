"""Dashboard dạng lịch: xem theo tuần và tháng, task hiện ngay trên lịch để dễ nhớ.

Toàn bộ lưới nằm trên một Canvas nên dù nhiều task vẫn nhẹ. Cách dùng theo các app lịch phổ
biến như TickTick: tô màu theo tag, kéo-thả để đổi ngày giờ, kéo mép dưới để đổi thời lượng,
bấm ô trống để thêm việc đúng vào ngày giờ đó.
"""
import tkinter as tk
from collections import namedtuple
from datetime import date, datetime, time, timedelta

import customtkinter as ctk
from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import AppearanceModeTracker
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from ..db import task_tag_names
from ..lunar import lunar_label
from ..quickparse import parse
from ..schedule import (ALL_DAY_TIME, WEEKDAY_SHORT, arrange_overlaps, calendar_items, days_in_month, from_text, month_days, to_text,
                        week_start)
from ..win32 import set_window_rounded
from . import theme
from .editor import TaskEditor
from .theme import (ACCENT, BG, BORDER, CARD, CARD_HOVER, FILL, GREEN, Icon, MUTED, ON_FILL, RED, SIDEBAR, TEXT, blend, resolve, tag_edge)
from .widgets import Card, Chip, FontCache, IconButton, TagChip, field, secondary_button, segmented

MODES = {"Tuần": "week", "Tháng": "month"}
LABELS = {mode: label for label, mode in MODES.items()}
MONTH_HEAD, DAY_NUMBER, CHIP_HEIGHT, CHIP_GAP = 30, 30, 21, 2
GUTTER, WEEK_HEAD, ALL_DAY_ROW, MAX_ALL_DAY_ROWS, HOUR_HEIGHT = 58, 62, 24, 3, 50
SIDE_PANEL_MIN_WIDTH = 940  # hẹp hơn mức này thì panel chi tiết nổi đè lên lịch thay vì ép lịch co lại
SNAP_MINUTES, MIN_EVENT_MINUTES, RESIZE_EDGE, DRAG_THRESHOLD = 15, 15, 7, 6
FIRST_VISIBLE_HOUR = 7
MINUTES_PER_DAY = 1440

Hit = namedtuple("Hit", "x0 y0 x1 y1 zone item day")  # zone: item | resize | more | day | slot | band | none

FONTS = {"chip": ("FONT_TEXT", 12, 0), "chip_done": ("FONT_TEXT", 12, 1), "day": ("FONT_SEMIBOLD", 13, 0), "head": ("FONT_SEMIBOLD", 12, 0),
         "small": ("FONT_TEXT", 11, 0), "event": ("FONT_SEMIBOLD", 12, 0), "event_done": ("FONT_SEMIBOLD", 12, 1),
         "date": ("FONT_DISPLAY", 18, 0), "badge": ("FONT_ICON", 27, 0), "badge_big": ("FONT_ICON", 32, 0), "glyph": ("FONT_ICON", 10, 0),
         "mark": ("FONT_ICON", 8, 0), "lunar": ("FONT_TEXT", 11, 0)}


def snap(minutes):
    return max(min(round(minutes / SNAP_MINUTES) * SNAP_MINUTES, MINUTES_PER_DAY - SNAP_MINUTES), 0)


def minutes_of(moment):
    return moment.hour * 60 + moment.minute


def add_on_day(app, content, day, minutes=None, tag_name=""):
    """Thêm việc vào một ngày. Câu gõ vào được hiểu theo chính ngày đó: '14h' là 14:00 của ngày vừa chọn."""
    fields = parse(content, datetime.combine(day, time.min))
    if not fields["due_at"]:
        if minutes is None:
            fields["due_at"], fields["all_day"] = f"{day.isoformat()} {ALL_DAY_TIME}", 1
        else:
            fields["due_at"] = to_text(datetime.combine(day, time.min) + timedelta(minutes=minutes))
    if tag_name:
        fields["tags"] = [*fields["tags"], tag_name]
    app.store.add_task(fields.pop("title"), **fields)
    app.changed()


class CalendarBoard(tk.Canvas):
    def __init__(self, master, page):
        super().__init__(master, highlightthickness=0, bd=0, bg=resolve(CARD), takefocus=1)
        self.page = page
        self.app = page.app
        self.store = page.app.store
        self.mode = "month"
        self.anchor = date.today()
        self.items = []
        self.hits = []
        self.hover = None
        self.selected_id = None
        self.scroll_y = None
        self.press = None
        self.drag = None
        self.grab_minutes = 0
        self.target = None
        self.week_geometry = (0, 0, 0, 0)
        self.month_geometry = (0, 0, 0)
        self.fonts = FontCache(FONTS)
        self.scale = 1.0
        self.colors = {}
        self.draw_pending = False

        self.bind("<Configure>", lambda _: self.schedule_draw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _: self._set_hover(None))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<MouseWheel>", self._on_wheel)
        AppearanceModeTracker.add(lambda _mode: self._on_theme(), self)

    # ---------- Dữ liệu ----------

    def visible_range(self):
        if self.mode == "week":
            first = week_start(self.anchor)
            return first, first + timedelta(days=7)
        days = month_days(self.anchor.year, self.anchor.month)
        return days[0], days[-1] + timedelta(days=1)

    def set_items(self, items):
        self.items = items
        self.schedule_draw()

    def _items_by_day(self):
        days = {}
        for item in self.items:
            days.setdefault(item.start.date(), []).append(item)
        return days

    def _on_theme(self):
        self.configure(bg=resolve(CARD))
        self.schedule_draw()

    def schedule_draw(self):
        if not self.draw_pending:
            self.draw_pending = True
            self.after_idle(self._paint)

    # ---------- Vẽ chung ----------

    def _paint(self):
        self.draw_pending = False
        if not self.winfo_exists() or self.drag:
            return
        self.delete("all")
        self.hits = []
        self.scale = ScalingTracker.get_widget_scaling(self)
        self.fonts.rescale(self.scale)
        self.colors = {name: resolve(pair) for name, pair in (
            ("card", CARD), ("hover", CARD_HOVER), ("border", BORDER), ("text", TEXT), ("muted", MUTED), ("accent", ACCENT),
            ("fill", FILL), ("on_fill", ON_FILL), ("red", RED), ("green", GREEN), ("dim", SIDEBAR), ("bg", BG))}
        width, height = self.winfo_width(), self.winfo_height()
        if width > 60 and height > 60:
            (self._paint_month if self.mode == "month" else self._paint_week)(width, height)

    def _scaled(self, value):
        return round(value * self.scale)

    def _edge(self, item):
        """Màu của mục theo tag đầu tiên, không có tag thì theo ưu tiên."""
        names = task_tag_names(item.task)
        if names:
            return resolve(tag_edge(self.app.tag_color(names[0])))
        return resolve(theme.PRIORITY_COLORS[item.task["priority"]] if item.task["priority"] else ACCENT)

    def _paint_overdue_mark(self, x, y, item):
        """Chấm đỏ cho việc quá hạn: giữ nguyên màu tag để vẫn nhận ra việc thuộc nhóm nào."""
        task = item.task
        if not task["done_at"] and not item.copy and task["due_at"] and from_text(task["due_at"]) < datetime.now():
            self.create_text(x, y, text=Icon.DOT, anchor="e", font=self.fonts.get("mark"), fill=self.colors["red"])

    def _fill_for(self, item, hovered):
        strength = 0.12 if item.task["done_at"] or item.copy else 0.26
        if hovered:
            strength += 0.14
        return blend(self._edge(item), self.colors["card"], strength)

    def _label_color(self, item):
        return self.colors["muted"] if item.task["done_at"] or item.copy else self.colors["text"]

    def _is_hovered(self, item):
        return self.hover is not None and self.hover.item is not None and self.hover.item.task["id"] == item.task["id"]

    # ---------- Tháng ----------

    def _paint_month(self, width, height):
        days = month_days(self.anchor.year, self.anchor.month)
        rows = len(days) // 7
        head = self._scaled(MONTH_HEAD)
        cell_w, cell_h = width / 7, (height - head) / rows
        self.month_geometry = (head, cell_w, cell_h)
        for column, name in enumerate(WEEKDAY_SHORT):
            self.create_text((column + 0.5) * cell_w, head / 2, text=name, font=self.fonts.get("head"), fill=self.colors["muted"])
        today = date.today()
        by_day = self._items_by_day()
        for index, day in enumerate(days):
            x0, y0 = index % 7 * cell_w, head + index // 7 * cell_h
            x1, y1 = x0 + cell_w, y0 + cell_h
            self.hits.append(Hit(x0, y0, x1, y1, "day", None, day))
            if day == today:
                self.create_rectangle(x0, y0, x1, y1, outline="", fill=blend(self.colors["fill"], self.colors["card"], 0.13))
            elif day.month != self.anchor.month:
                self.create_rectangle(x0, y0, x1, y1, outline="", fill=self.colors["dim"])
            elif self.hover and self.hover.zone == "day" and self.hover.day == day:
                self.create_rectangle(x0, y0, x1, y1, outline="", fill=self.colors["hover"])
        for row in range(rows + 1):
            y = head + row * cell_h
            self.create_line(0, y, width, y, fill=self.colors["border"])
        for column in range(1, 7):
            self.create_line(column * cell_w, head, column * cell_w, height, fill=self.colors["border"])
        for index, day in enumerate(days):
            x0, y0 = index % 7 * cell_w, head + index // 7 * cell_h
            self._paint_month_cell(day, x0, y0, cell_w, cell_h, by_day.get(day, []), today)

    def _paint_month_cell(self, day, x0, y0, cell_w, cell_h, items, today):
        number_x, number_y = x0 + self._scaled(17), y0 + self._scaled(15)
        if day == today:
            self.create_text(number_x, number_y, text=Icon.DOT, font=self.fonts.get("badge"), fill=self.colors["fill"])
            color = self.colors["on_fill"]
        else:
            color = self.colors["text"] if day.month == self.anchor.month else self.colors["muted"]
        self.create_text(number_x, number_y, text=str(day.day), font=self.fonts.get("day"), fill=color)
        self._paint_lunar(x0 + cell_w - self._scaled(7), number_y, day, "e")
        chip_h, gap = self._scaled(CHIP_HEIGHT), self._scaled(CHIP_GAP)
        top = y0 + self._scaled(DAY_NUMBER)
        capacity = max(int((cell_h - self._scaled(DAY_NUMBER) - gap) // (chip_h + gap)), 0)
        items = sorted(self._one_per_task(items), key=lambda item: bool(item.task["done_at"]))  # việc chưa xong lên trước
        shown = items if len(items) <= capacity else items[:max(capacity - 1, 0)]
        x = x0 + self._scaled(3)
        chip_w = cell_w - self._scaled(6)
        for offset, item in enumerate(shown):
            self._paint_chip(x, top + offset * (chip_h + gap), chip_w, chip_h, item)
        hidden = len(items) - len(shown)
        if hidden > 0:
            y = top + len(shown) * (chip_h + gap)
            label = f"+{hidden} việc nữa"
            self.create_text(x + self._scaled(6), y + chip_h / 2, text=label, anchor="w", font=self.fonts.get("small"),
                             fill=self.colors["accent"])
            self.hits.append(Hit(x, y, x + chip_w, y + chip_h, "more", None, day))

    def _paint_lunar(self, x, y, day, anchor):
        """Ngày âm nhỏ cạnh ngày dương. Mùng một ghi cả tháng và đổi màu cho dễ thấy."""
        label = lunar_label(day)
        self.create_text(x, y, text=label, anchor=anchor, font=self.fonts.get("lunar"), fill=self.colors["accent" if "/" in label else "muted"])

    @staticmethod
    def _one_per_task(items):
        """Trên ô tháng, mỗi việc chỉ hiện một lần dù có cả khối giờ lẫn hạn chót trong ngày."""
        seen, unique = set(), []
        for item in items:
            if item.task["id"] not in seen:
                seen.add(item.task["id"])
                unique.append(item)
        return unique

    def _paint_chip(self, x, y, width, height, item):
        hovered = self._is_hovered(item)
        edge = self._edge(item)
        self.create_rectangle(x, y, x + width, y + height, outline="", fill=self._fill_for(item, hovered))
        self.create_rectangle(x, y, x + self._scaled(3), y + height, outline="", fill=edge)
        if item.task["id"] == self.selected_id:
            self.create_rectangle(x, y, x + width, y + height, outline=self.colors["accent"])
        prefix = "" if item.all_day else f"{item.start:%H:%M} "
        font = "chip_done" if item.task["done_at"] else "chip"
        room = width - self._scaled(20)
        self.create_text(x + self._scaled(7), y + height / 2, anchor="w", font=self.fonts.get(font), fill=self._label_color(item),
                         text=self.fonts.fit(font, prefix + item.task["title"], room))
        self._paint_overdue_mark(x + width - self._scaled(4), y + height / 2, item)
        self.hits.append(Hit(x, y, x + width, y + height, "item", item, item.start.date()))

    # ---------- Tuần ----------

    def _paint_week(self, width, height):
        first = week_start(self.anchor)
        days = [first + timedelta(days=offset) for offset in range(7)]
        by_day = self._items_by_day()
        whole_day = {day: self._one_per_task([item for item in by_day.get(day, []) if item.all_day]) for day in days}
        rows = min(max(max(len(items) for items in whole_day.values()), 1), MAX_ALL_DAY_ROWS)
        gutter, head = self._scaled(GUTTER), self._scaled(WEEK_HEAD)
        band = self._scaled(rows * ALL_DAY_ROW + 8)
        top = head + band
        column_w = (width - gutter) / 7
        hour_h = self._scaled(HOUR_HEIGHT)
        limit = max(24 * hour_h - (height - top), 0)
        if self.scroll_y is None:
            self.scroll_y = self._opening_scroll(hour_h)
        self.scroll_y = max(min(self.scroll_y, limit), 0)
        self.week_geometry = (gutter, top, column_w, hour_h)
        today = date.today()
        self._paint_hours(width, height, gutter, top, hour_h)
        for index, day in enumerate(days):
            x = gutter + index * column_w
            self.hits.append(Hit(x, top, x + column_w, height, "slot", None, day))
            if day == today:
                self.create_rectangle(x, top, x + column_w, height, outline="", fill=blend(self.colors["fill"], self.colors["card"], 0.10))
                self.tag_lower(self.find_all()[-1])
            self.create_line(x, top, x, height, fill=self.colors["border"])
            self._paint_day_events(x, column_w, top, height, hour_h, [item for item in by_day.get(day, []) if not item.all_day])
        self._paint_now_line(days, gutter, column_w, top, hour_h, width)
        self._paint_week_head(days, whole_day, gutter, column_w, head, top, width, rows, today)

    def _opening_scroll(self, hour_h):
        hour = datetime.now().hour - 1 if week_start(self.anchor) == week_start(date.today()) else FIRST_VISIBLE_HOUR
        return max(hour, 0) * hour_h

    def _paint_hours(self, width, height, gutter, top, hour_h):
        for hour in range(24):
            y = top + hour * hour_h - self.scroll_y
            if top - hour_h <= y <= height:
                self.create_line(gutter, y, width, y, fill=self.colors["border"])
                if hour:
                    self.create_text(gutter - self._scaled(8), y, text=f"{hour:02d}:00", anchor="e", font=self.fonts.get("small"),
                                     fill=self.colors["muted"])

    def _paint_day_events(self, x, column_w, top, height, hour_h, items):
        pad = self._scaled(2)
        for item, column, columns in arrange_overlaps(items):
            start = minutes_of(item.start)
            end = MINUTES_PER_DAY if item.end.date() != item.start.date() else minutes_of(item.end)
            y0 = top + start / 60 * hour_h - self.scroll_y
            y1 = y0 + max((end - start) / 60 * hour_h, self._scaled(22))
            if y1 < top or y0 > height:
                continue
            width = (column_w - 2 * pad) / columns
            left = x + pad + column * width
            self._paint_event(left, y0 + 1, width - 1, y1 - y0 - 2, item)

    def _paint_event(self, x, y, width, height, item):
        hovered = self._is_hovered(item)
        edge = self._edge(item)
        self.create_rectangle(x, y, x + width, y + height, outline="", fill=self._fill_for(item, hovered))
        self.create_rectangle(x, y, x + self._scaled(3), y + height, outline="", fill=edge)
        if item.task["id"] == self.selected_id:
            self.create_rectangle(x, y, x + width, y + height, outline=self.colors["accent"])
        font = "event_done" if item.task["done_at"] else "event"
        room = width - self._scaled(20)
        color = self._label_color(item)
        self._paint_overdue_mark(x + width - self._scaled(4), y + self._scaled(11), item)
        if height >= self._scaled(40):
            self.create_text(x + self._scaled(7), y + self._scaled(4), anchor="nw", font=self.fonts.get(font), fill=color,
                             text=self.fonts.fit(font, item.task["title"], room))
            span = f"{item.start:%H:%M}–{item.end:%H:%M}" if item.kind == "block" else f"Hạn {item.start:%H:%M}"
            self.create_text(x + self._scaled(7), y + self._scaled(22), anchor="nw", font=self.fonts.get("small"), fill=self.colors["muted"],
                             text=self.fonts.fit("small", span, room))
        else:
            self.create_text(x + self._scaled(7), y + height / 2, anchor="w", font=self.fonts.get(font), fill=color,
                             text=self.fonts.fit(font, f"{item.start:%H:%M} {item.task['title']}", room))
        self.hits.append(Hit(x, y, x + width, y + height, "item", item, item.start.date()))
        if not item.copy and not item.task["done_at"]:
            self.hits.append(Hit(x, y + height - self._scaled(RESIZE_EDGE), x + width, y + height, "resize", item, item.start.date()))

    def _paint_now_line(self, days, gutter, column_w, top, hour_h, width):
        now = datetime.now()
        if now.date() not in days:
            return
        y = top + minutes_of(now) / 60 * hour_h - self.scroll_y
        if y >= top:
            x = gutter + days.index(now.date()) * column_w
            self.create_line(x, y, x + column_w, y, fill=self.colors["red"], width=self._scaled(2))
            self.create_text(x, y, text=Icon.DOT, font=self.fonts.get("glyph"), fill=self.colors["red"])

    def _paint_week_head(self, days, whole_day, gutter, column_w, head, top, width, rows, today):
        self.create_rectangle(0, 0, width, top, outline="", fill=self.colors["card"])
        self.hits.append(Hit(0, 0, width, top, "none", None, None))
        self.create_text(gutter - self._scaled(8), head + (top - head) / 2, text="Cả ngày", anchor="e", font=self.fonts.get("small"),
                         fill=self.colors["muted"])
        for index, day in enumerate(days):
            x = gutter + index * column_w
            middle = x + column_w / 2
            self.create_text(middle, head * 0.26, text=WEEKDAY_SHORT[day.weekday()], font=self.fonts.get("head"),
                             fill=self.colors["accent"] if day == today else self.colors["muted"])
            if day == today:
                self.create_text(middle, head * 0.66, text=Icon.DOT, font=self.fonts.get("badge_big"), fill=self.colors["fill"])
            self.create_text(middle, head * 0.66, text=str(day.day), font=self.fonts.get("date"),
                             fill=self.colors["on_fill"] if day == today else self.colors["text"])
            self._paint_lunar(middle + self._scaled(21), head * 0.66, day, "w")
            self.hits.append(Hit(x, head, x + column_w, top, "band", None, day))
            self._paint_band_cell(x, head, column_w, whole_day[day], rows, day)
        self.create_line(0, head, width, head, fill=self.colors["border"])
        self.create_line(0, top - 1, width, top - 1, fill=self.colors["border"])
        for index in range(7):
            x = gutter + index * column_w
            self.create_line(x, 0, x, top, fill=self.colors["border"])

    def _paint_band_cell(self, x, head, column_w, items, rows, day):
        chip_h, gap = self._scaled(ALL_DAY_ROW - 3), self._scaled(3)
        left = x + self._scaled(2)
        width = column_w - self._scaled(4)
        shown = items if len(items) <= rows else items[:rows - 1]
        for offset, item in enumerate(shown):
            self._paint_chip(left, head + gap + offset * (chip_h + gap), width, chip_h, item)
        if len(items) > len(shown):
            y = head + gap + len(shown) * (chip_h + gap)
            self.create_text(left + self._scaled(6), y + chip_h / 2, text=f"+{len(items) - len(shown)} việc nữa", anchor="w",
                             font=self.fonts.get("small"), fill=self.colors["accent"])

    # ---------- Tương tác ----------

    def _hit_at(self, x, y):
        for hit in reversed(self.hits):
            if hit.x0 <= x < hit.x1 and hit.y0 <= y < hit.y1:
                return hit
        return None

    def _set_hover(self, hit):
        before, self.hover = self.hover, hit
        same_item = (before and before.item and before.item.task["id"]) == (hit and hit.item and hit.item.task["id"])
        same_day = (before and before.zone == "day" and before.day) == (hit and hit.zone == "day" and hit.day)
        if not (same_item and same_day):
            self.schedule_draw()

    def _on_motion(self, event):
        hit = self._hit_at(event.x, event.y)
        self._set_hover(hit)
        zone = hit.zone if hit else None
        self.configure(cursor={"resize": "sb_v_double_arrow", "item": "hand2", "more": "hand2", "day": "plus", "slot": "plus", "band": "plus"}.get(zone, ""))

    def _on_wheel(self, event):
        if self.mode == "week":
            self.scroll_y = (self.scroll_y or 0) - event.delta / 120 * self.week_geometry[3]
            self.schedule_draw()

    def _on_press(self, event):
        self.focus_set()
        self.press = (self._hit_at(event.x, event.y), event.x, event.y)
        self.drag = None
        self.target = None

    def _can_drag(self, hit):
        return hit is not None and hit.zone in ("item", "resize") and not hit.item.copy and not hit.item.task["done_at"]

    def _on_drag(self, event):
        if not self.press:
            return
        hit, x0, y0 = self.press
        if not self._can_drag(hit):
            return
        if self.drag is None:
            if abs(event.x - x0) + abs(event.y - y0) < self._scaled(DRAG_THRESHOLD):
                return
            self.drag = hit.zone
            if self.mode == "week" and not hit.item.all_day:
                self.grab_minutes = self._pointer_minutes(y0) - minutes_of(hit.item.start)
            else:
                self.grab_minutes = 0
        self.delete("ghost")
        if self.mode == "month":
            self._ghost_month(event)
        elif self.drag == "resize":
            self._ghost_resize(event, hit.item)
        else:
            self._ghost_week(event, hit.item)

    def _pointer_minutes(self, y):
        _, top, _, hour_h = self.week_geometry
        return (y - top + (self.scroll_y or 0)) / hour_h * 60

    def _ghost_month(self, event):
        head, cell_w, cell_h = self.month_geometry
        days = month_days(self.anchor.year, self.anchor.month)
        column = max(min(int(event.x // cell_w), 6), 0)
        row = max(min(int((event.y - head) // cell_h), len(days) // 7 - 1), 0)
        self.target = days[row * 7 + column]
        x, y = column * cell_w, head + row * cell_h
        self.create_rectangle(x + 1, y + 1, x + cell_w - 1, y + cell_h - 1, outline=self.colors["accent"], width=self._scaled(2), tags="ghost")

    def _ghost_week(self, event, item):
        gutter, top, column_w, hour_h = self.week_geometry
        column = max(min(int((event.x - gutter) // column_w), 6), 0)
        day = week_start(self.anchor) + timedelta(days=column)
        x = gutter + column * column_w
        if event.y < top:
            self.target = (day, None)
            self.create_rectangle(x + 1, self._scaled(WEEK_HEAD) + 1, x + column_w - 1, top - 2, outline=self.colors["accent"],
                                  width=self._scaled(2), tags="ghost")
            return
        start = snap(self._pointer_minutes(event.y) - self.grab_minutes)
        self.target = (day, start)
        span = 60 if item.all_day else max((item.end - item.start).total_seconds() / 60, MIN_EVENT_MINUTES)
        y0 = top + start / 60 * hour_h - self.scroll_y
        y1 = y0 + span / 60 * hour_h
        self.create_rectangle(x + 2, y0, x + column_w - 2, y1, outline=self.colors["accent"], width=self._scaled(2), tags="ghost")
        self.create_text(x + self._scaled(8), y0 + self._scaled(4), anchor="nw", text=f"{start // 60:02d}:{start % 60:02d}",
                         font=self.fonts.get("event"), fill=self.colors["accent"], tags="ghost")

    def _ghost_resize(self, event, item):
        gutter, top, column_w, hour_h = self.week_geometry
        column = (item.start.date() - week_start(self.anchor)).days
        x = gutter + column * column_w
        start = minutes_of(item.start)
        end = max(snap(self._pointer_minutes(event.y)), start + MIN_EVENT_MINUTES)
        self.target = end - start
        y0 = top + start / 60 * hour_h - self.scroll_y
        y1 = top + end / 60 * hour_h - self.scroll_y
        self.create_rectangle(x + 2, y0, x + column_w - 2, y1, outline=self.colors["accent"], width=self._scaled(2), tags="ghost")
        self.create_text(x + self._scaled(8), y1 - self._scaled(4), anchor="sw", text=f"{self.target} phút", font=self.fonts.get("event"),
                         fill=self.colors["accent"], tags="ghost")

    def _on_release(self, event):
        press, self.press = self.press, None
        dragged, self.drag = self.drag, None
        self.delete("ghost")
        if press is None:
            return
        hit = press[0]
        if dragged:
            if self.target is not None:
                self.page.apply_drop(hit.item, dragged, self.target)
            self.schedule_draw()
            return
        release_hit = self._hit_at(event.x, event.y)
        if hit is None or release_hit is None or release_hit.zone != hit.zone:
            return
        if hit.zone in ("item", "resize"):
            self.selected_id = hit.item.task["id"]
            self.schedule_draw()
            self.page.open_editor(hit.item.task["id"])
        elif hit.zone == "more":
            self.page.show_week_of(hit.day)
        elif hit.zone == "day":
            self.page.quick_add(event, hit.day, None)
        elif hit.zone == "band":
            self.page.quick_add(event, hit.day, None)
        elif hit.zone == "slot":
            self.page.quick_add(event, hit.day, snap(self._pointer_minutes(event.y)))


class QuickPopover(tk.Toplevel):
    """Ô nhập nhỏ hiện ngay tại ô lịch vừa bấm."""
    WIDTH = 300

    def __init__(self, master, x, y, label, on_submit):
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.on_submit = on_submit
        scale = ScalingTracker.get_widget_scaling(master)
        body = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, border_width=1, border_color=ACCENT)
        body.pack(fill="both", expand=True)
        ctk.CTkLabel(body, text=label, font=theme.semibold(12), text_color=ACCENT, anchor="w", height=20).pack(fill="x", padx=12, pady=(10, 2))
        self.entry = field(body, width=self.WIDTH - 24, placeholder_text="Tên việc, Enter để lưu, Esc để đóng")
        self.entry.pack(padx=12, pady=(0, 12))
        self.entry.bind("<Return>", self._submit)
        self.entry.bind("<Escape>", lambda _: self.destroy())
        self.bind("<FocusOut>", lambda _: self.after(80, self._close_if_unfocused))
        width, height = round(self.WIDTH * scale), round(92 * scale)
        x = min(x, master.winfo_screenwidth() - width - 8)
        y = min(y, master.winfo_screenheight() - height - 56)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.update_idletasks()
        set_window_rounded(self.winfo_id())
        self.entry._entry.focus_force()

    def _close_if_unfocused(self):
        if self.winfo_exists() and self.focus_displayof() is None:
            self.destroy()

    def _submit(self, _event=None):
        content = self.entry.get()
        if content.strip():
            self.on_submit(content)
        self.destroy()
        return "break"


class CalendarPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=BG)
        self.app = app
        self.store = app.store
        self.quick = self  # Ctrl+N trên trang lịch mở ô thêm việc cho hôm nay
        self.tag_id = 0
        self.tag_name = ""
        self.editor = None  # panel khá nặng nên chỉ dựng khi mở lần đầu
        self.editor_open = False
        self.popover = None
        self.legend_signature = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=(24, 12), pady=(18, 8))
        self.mode_switch = segmented(header, list(MODES), self.set_mode, width=132, dynamic_resizing=False)
        self.mode_switch.pack(side="right")  # xếp trước để không bị bóp khi thiếu chỗ
        self.title_label = ctk.CTkLabel(header, text="", font=theme.display(25), text_color=TEXT, anchor="w", height=34)
        self.title_label.pack(side="left")
        IconButton(header, Icon.LEFT, lambda: self.step(-1), size=32, color=TEXT).pack(side="left", padx=(12, 0))
        IconButton(header, Icon.RIGHT, lambda: self.step(1), size=32, color=TEXT).pack(side="left")
        secondary_button(header, "Hôm nay", self.go_today, width=76).pack(side="left", padx=(6, 0))
        self.summary = ctk.CTkLabel(header, text="", font=theme.text(13), text_color=MUTED, height=34)
        self.summary.pack(side="left", padx=(14, 0))

        legend_row = ctk.CTkFrame(self, fg_color="transparent", height=30)
        legend_row.grid(row=1, column=0, sticky="ew", padx=(24, 12), pady=(0, 8))
        self.legend = ctk.CTkFrame(legend_row, fg_color="transparent")
        self.legend.pack(side="left")
        self.hint = ctk.CTkLabel(legend_row, text="Bấm ô trống để thêm · kéo để dời lịch", font=theme.text(12), text_color=MUTED)
        legend_row.bind("<Configure>", lambda _: self._fit_hint())

        card = Card(self)
        card.grid(row=2, column=0, sticky="nsew", padx=(24, 12), pady=(0, 20))
        self.board = CalendarBoard(card, self)
        self.board.pack(fill="both", expand=True, padx=2, pady=2)
        self.board.mode = self.store.setting("calendar_mode")
        self.mode_switch.set(LABELS[self.board.mode])
        for key, action in (("<Left>", lambda: self.step(-1)), ("<Right>", lambda: self.step(1)), ("t", self.go_today),
                            ("w", lambda: self.set_mode("Tuần")), ("m", lambda: self.set_mode("Tháng"))):
            self.board.bind(key, lambda _event, run=action: run())

    # ---------- Điều hướng ----------

    def set_mode(self, label):
        mode = MODES[label]
        self.mode_switch.set(label)
        if mode != self.board.mode:
            self.board.mode = mode
            self.board.scroll_y = None
            self.store.set_setting("calendar_mode", mode)
            self.refresh(datetime.now())

    def step(self, direction):
        anchor = self.board.anchor
        if self.board.mode == "week":
            self.board.anchor = anchor + timedelta(days=7 * direction)
        else:
            index = anchor.year * 12 + anchor.month - 1 + direction
            year, month = index // 12, index % 12 + 1
            self.board.anchor = date(year, month, min(anchor.day, days_in_month(year, month)))
        self.board.scroll_y = None if self.board.mode == "week" else self.board.scroll_y
        self.refresh(datetime.now())

    def go_today(self):
        self.board.anchor = date.today()
        self.board.scroll_y = None
        self.refresh(datetime.now())

    def show_week_of(self, day):
        self.board.anchor = day
        self.set_mode("Tuần")

    def set_filter(self, tag_id, name):
        self.tag_id, self.tag_name = tag_id, name
        self._render_legend(force=True)
        self.refresh(datetime.now())

    # ---------- Dữ liệu ----------

    def _heading(self):
        anchor = self.board.anchor
        if self.board.mode == "month":
            return f"Tháng {anchor.month}, {anchor.year}"
        first = week_start(anchor)
        last = first + timedelta(days=6)
        if first.month == last.month:
            return f"{first.day}–{last.day} tháng {last.month}, {last.year}"
        return f"{first.day}/{first.month} – {last.day}/{last.month}, {last.year}"

    def refresh(self, now):
        first, last = self.board.visible_range()
        items = calendar_items(self.store.calendar_tasks(first, last, self.tag_id), first, last)
        self.board.set_items(items)
        self.title_label.configure(text=self._heading())
        real = {item.task["id"]: item.task for item in items if not item.copy}
        finished = sum(1 for task in real.values() if task["done_at"])
        late = sum(1 for task in real.values() if not task["done_at"] and task["due_at"] and from_text(task["due_at"]) < now)
        parts = [f"{len(real)} việc"]
        if late:
            parts.append(f"{late} quá hạn")
        if finished:
            parts.append(f"{finished} đã xong")
        self.summary.configure(text=" · ".join(parts))
        self._render_legend()

    def _render_legend(self, force=False):
        tags = [(row["id"], row["name"], row["color"]) for row in self.store.tags()]
        if tags == self.legend_signature and not force:
            return
        self.legend_signature = tags
        for child in self.legend.winfo_children():
            child.destroy()
        everything = Chip(self.legend, "Tất cả", lambda: self.set_filter(0, ""), width=60)
        everything.set_active(not self.tag_id)
        everything.pack(side="left", padx=(0, 6))
        for tag_id, name, color in tags:
            chip = TagChip(self.legend, name, color, lambda i=tag_id, n=name: self.set_filter(0 if self.tag_id == i else i, "" if self.tag_id == i else n))
            chip.set_active(self.tag_id == tag_id)
            chip.pack(side="left", padx=(0, 6))
        self.after_idle(self._fit_hint)

    def _fit_hint(self):
        """Dòng gợi ý chỉ hiện khi đủ chỗ, không để bị cắt giữa chừng."""
        row = self.hint.master
        fits = self.legend.winfo_reqwidth() + self.hint.winfo_reqwidth() + 24 <= row.winfo_width()
        if fits and not self.hint.winfo_ismapped():
            self.hint.pack(side="right")
        elif not fits and self.hint.winfo_ismapped():
            self.hint.pack_forget()

    # ---------- Thêm và dời việc ----------

    def focus_entry(self):
        board = self.board
        self.quick_add(None, date.today(), None, (board.winfo_rootx() + 40, board.winfo_rooty() + 40))

    def quick_add(self, event, day, minutes, position=None):
        if self.popover is not None and self.popover.winfo_exists():
            self.popover.destroy()
        if event is not None:
            position = (event.x_root + 8, event.y_root + 8)
        label = f"{WEEKDAY_SHORT[day.weekday()]} {day:%d/%m}"
        if minutes is not None:
            label += f", {minutes // 60:02d}:{minutes % 60:02d}"
        self.popover = QuickPopover(self.board, *position, label, lambda content: add_on_day(self.app, content, day, minutes, self.tag_name))

    def apply_drop(self, item, zone, target):
        task = item.task
        task_id = task["id"]
        before = {key: task[key] for key in ("due_at", "all_day", "block_start", "block_minutes", "snooze_until")}
        if zone == "resize":
            self.store.update_task(task_id, block_start=to_text(item.start), block_minutes=target)
            message = f"{task['title']}: {target} phút"
        elif self.board.mode == "month":
            delta = target - item.start.date()
            if not delta:
                return
            self.store.move_on_calendar(task_id, item.kind, delta)
            message = f"Đã dời sang {WEEKDAY_SHORT[target.weekday()]} {target:%d/%m}"
        else:
            day, minutes = target
            if minutes is None:
                if item.all_day and day == item.start.date():
                    return
                self.store.update_task(task_id, due_at=f"{day.isoformat()} {ALL_DAY_TIME}", all_day=1, block_start=None, snooze_until=None)
                message = f"Đã dời sang cả ngày {WEEKDAY_SHORT[day.weekday()]} {day:%d/%m}"
            else:
                moment = datetime.combine(day, time.min) + timedelta(minutes=minutes)
                if item.all_day:
                    self.store.update_task(task_id, due_at=to_text(moment), all_day=0, snooze_until=None)
                elif moment == item.start:
                    return
                else:
                    self.store.move_on_calendar(task_id, item.kind, moment - item.start)
                message = f"Đã dời sang {WEEKDAY_SHORT[day.weekday()]} {day:%d/%m}, {moment:%H:%M}"
        self.app.snackbar.show(message, "Hoàn tác", lambda: self._undo_drop(task_id, before))
        self.app.changed()

    def _undo_drop(self, task_id, before):
        self.store.update_task(task_id, **before)
        self.app.changed()

    # ---------- Panel chi tiết ----------

    def open_editor(self, task_id):
        if self.editor is None:
            self.editor = TaskEditor(self, self.app)
        if not self.editor_open:
            room = self.winfo_width() / ScalingTracker.get_widget_scaling(self)
            column, padding = (1, (0, 24)) if room >= SIDE_PANEL_MIN_WIDTH else (0, (0, 12))
            self.editor.grid(row=0, column=column, rowspan=3, sticky="nse", padx=padding, pady=(18, 20))
            self.editor.lift()
            self.editor_open = True
            self.summary.pack_forget()
        self.board.selected_id = task_id
        self.board.schedule_draw()
        self.editor.load(task_id)

    def close_editor(self):
        if self.editor_open:
            self.editor.grid_remove()
            self.editor_open = False
            self.editor.task_id = None
            self.editor.task = None
            self.summary.pack(side="left", padx=(14, 0))
        self.board.selected_id = None
        self.board.schedule_draw()
