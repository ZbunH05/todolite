"""Các widget tự vẽ. Mọi thứ dài/lặp lại đều nằm trên một Canvas duy nhất, vì mỗi widget
CustomTkinter là cả một cụm widget Tk: 300 dòng task dựng bằng CTk sẽ ngốn RAM và giật khi cuộn.
"""
import calendar
import tkinter as tk
import tkinter.font as tkfont
from bisect import bisect_right
from datetime import date, datetime, timedelta

import customtkinter as ctk
from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import AppearanceModeTracker
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from ..db import tag_key, task_tag_names
from ..quickparse import describe, parse, tag_prefix
from ..schedule import WEEKDAY_SHORT, block_window, day_label, from_text, humanize, when_label
from ..win32 import set_window_rounded
from . import theme
from .theme import (ACCENT, ACCENT_SOFT, AMBER, BORDER, CARD, CARD_HOVER, CHART_BAR, FIELD, FILL, FILL_HOVER, GREEN, Icon, MUTED,
                    ON_FILL, RED, SEGMENT_SELECTED, TEXT, TRACK, blend, resolve, tag_edge, tag_tint)

QUICK_HINT = "Gõ tự nhiên: mai 9h · t6 14:00 · 15/11 · hằng tuần · !1 ưu tiên · #học-tập · ~50p khối giờ"


class Card(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        options = dict(fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        super().__init__(master, **(options | kwargs))


class IconButton(ctk.CTkButton):
    def __init__(self, master, glyph, command, size=30, color=MUTED, hover=CARD_HOVER):
        super().__init__(master, text=glyph, command=command, width=size, height=size, corner_radius=8,
                         fg_color="transparent", hover_color=hover, text_color=color, font=theme.icon(14))


class Chip(ctk.CTkButton):
    """Nút nhỏ bật/tắt."""

    def __init__(self, master, label, command, width=0):
        super().__init__(master, text=label, command=command, height=26, width=width or 44, corner_radius=13,
                         border_width=1, font=theme.text(12))
        self.active = None
        self.set_active(False)

    def set_active(self, active):
        if active != self.active:  # mỗi lần configure là một lần vẽ lại toàn bộ nút
            self.active = active
            self._apply_state(active)

    def _apply_state(self, active):
        self.configure(fg_color=ACCENT_SOFT if active else "transparent", hover_color=ACCENT_SOFT if active else CARD_HOVER,
                       text_color=TEXT if active else MUTED, border_color=ACCENT if active else BORDER)


class TagChip(Chip):
    """Chip mang màu của tag: viền màu khi chưa chọn, nền màu khi đã chọn."""

    def __init__(self, master, label, color, command, width=0):
        self.tag_color = color
        super().__init__(master, label, command, width)

    def _apply_state(self, active):
        tint, edge = tag_tint(self.tag_color), tag_edge(self.tag_color)
        self.configure(fg_color=tint if active else "transparent", hover_color=tint, text_color=TEXT if active else MUTED,
                       border_color=edge if active else (blend(edge[0], CARD[0], 0.45), blend(edge[1], CARD[1], 0.45)))


def primary_button(master, label, command, **kwargs):
    options = dict(height=32, corner_radius=8, fg_color=FILL, hover_color=FILL_HOVER, text_color=ON_FILL,
                   font=theme.semibold(13))
    return ctk.CTkButton(master, text=label, command=command, **(options | kwargs))


def secondary_button(master, label, command, **kwargs):
    options = dict(height=32, corner_radius=8, fg_color="transparent", hover_color=CARD_HOVER, text_color=TEXT,
                   border_width=1, border_color=BORDER, font=theme.text(13))
    return ctk.CTkButton(master, text=label, command=command, **(options | kwargs))


def segmented(master, values, command, **kwargs):
    options = dict(height=30, corner_radius=8, font=theme.text(12), selected_color=SEGMENT_SELECTED,
                   selected_hover_color=SEGMENT_SELECTED, unselected_color=FIELD, fg_color=FIELD,
                   unselected_hover_color=CARD_HOVER, text_color=TEXT)
    return ctk.CTkSegmentedButton(master, values=values, command=command, **(options | kwargs))


def field(master, **kwargs):
    options = dict(height=34, corner_radius=8, border_width=1, border_color=BORDER, fg_color=FIELD, text_color=TEXT,
                   placeholder_text_color=MUTED, font=theme.text(13))
    entry = ctk.CTkEntry(master, **(options | kwargs))
    entry.bind("<FocusIn>", lambda _: entry.configure(border_color=ACCENT))
    entry.bind("<FocusOut>", lambda _: entry.configure(border_color=BORDER))
    return entry


def set_text(entry, value):
    """Gán nội dung ô nhập. CTkEntry coi ô mới tạo là đang focus nên sẽ không hiện lại
    placeholder sau khi xoá, phải báo trạng thái focus thật cho nó trước."""
    entry._is_focused = entry.focus_get() is entry._entry
    entry.delete(0, "end")
    if value:
        entry.insert(0, value)


class FontCache:
    """Font vẽ trên Canvas theo tỉ lệ DPI, kèm bộ nhớ đệm đo chữ."""
    MEASURE_LIMIT = 4000

    def __init__(self, specs):
        self.specs = specs  # tên: (thuộc tính font trong theme, cỡ px, gạch ngang)
        self.scale = None
        self.fonts = {}
        self.widths = {}

    def rescale(self, scale):
        if scale != self.scale:
            self.scale = scale
            self.fonts = {}
            self.widths = {}

    def get(self, name):
        if name not in self.fonts:
            family, size, overstrike = self.specs[name]
            self.fonts[name] = tkfont.Font(family=getattr(theme, family), size=-round(size * self.scale), overstrike=overstrike)
        return self.fonts[name]

    def measure(self, name, content):
        key = (name, content)
        if key not in self.widths:
            if len(self.widths) > self.MEASURE_LIMIT:
                self.widths.clear()
            self.widths[key] = self.get(name).measure(content)
        return self.widths[key]

    def fit(self, name, content, width):
        """Cắt chữ vừa bề rộng, thêm dấu ba chấm."""
        if self.measure(name, content) <= width:
            return content
        low, high = 0, len(content)
        while low < high:
            middle = (low + high + 1) // 2
            if self.measure(name, content[:middle] + "…") <= width:
                low = middle
            else:
                high = middle - 1
        return content[:low].rstrip() + "…" if low else ""


class QuickEntry(ctk.CTkFrame):
    """Ô thêm việc bằng câu tự nhiên, xem trước phần đã hiểu ngay khi gõ."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.entry = field(self, height=40, placeholder_text="Thêm việc mới…   (Ctrl+N)", font=theme.text(14))
        self.entry.pack(fill="x")
        self.entry.bind("<KeyRelease>", self._preview)
        self.entry.bind("<Return>", self._submit)
        self.entry.bind("<Tab>", self._complete_tag)
        self.preview = ctk.CTkLabel(self, text=QUICK_HINT, anchor="w", height=20, font=theme.text(12), text_color=MUTED)
        self.preview.pack(fill="x", pady=(2, 0))

    def focus_entry(self):
        self.entry.focus_set()

    def _matching_tags(self, prefix):
        key = tag_key(prefix)
        return [row["name"] for row in self.app.store.tags() if tag_key(row["name"]).startswith(key)]

    def _preview(self, _event=None):
        content = self.entry.get()
        prefix = tag_prefix(content)
        matches = self._matching_tags(prefix) if prefix is not None else []
        if matches:
            names = "   ".join(f"#{name}" for name in matches[:6])
            self.preview.configure(text=f"{names}   ·   Tab để chọn", text_color=ACCENT)
            return
        summary = describe(parse(content), tag_label=self.app.store.tag_label) if content.strip() else ""
        self.preview.configure(text=f"→  {summary}" if summary else QUICK_HINT, text_color=ACCENT if summary else MUTED)

    def _complete_tag(self, _event=None):
        content = self.entry.get()
        prefix = tag_prefix(content)
        matches = self._matching_tags(prefix) if prefix is not None else []
        if not matches:
            return None
        head = content[:len(content) - len(prefix) - 1]
        set_text(self.entry, f"{head}#{matches[0].replace(' ', '-')} ")
        self.entry._entry.icursor("end")
        self._preview()
        return "break"

    def _submit(self, _event=None):
        content = self.entry.get()
        if content.strip():
            fields = parse(content)
            self.app.add_task(fields)
            set_text(self.entry, "")
            self._preview()
        return "break"


class TagPicker(ctk.CTkFrame):
    """Chọn nhiều tag bằng chip màu, tự xuống dòng; có thể tạo tag mới ngay tại chỗ."""
    WIDTH = 318
    GAP = 6

    def __init__(self, master, app, on_change):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.on_change = on_change
        self.selected = []
        self.signature = None
        self.chips = {}
        self.rows = ctk.CTkFrame(self, fg_color="transparent")
        self.rows.pack(fill="x")
        self.entry = field(self, height=30, placeholder_text="Tên tag mới, Enter để thêm")
        self.entry.bind("<Return>", self._add)
        self.entry.bind("<Escape>", lambda _: self._hide_entry())

    def set_selected(self, names):
        self.selected = list(names)
        tags = [(row["name"], row["color"]) for row in self.app.store.tags()]
        if tags != self.signature:
            self.signature = tags
            self._render(tags)
        for name, chip in self.chips.items():
            chip.set_active(name in self.selected)

    def _render(self, tags):
        for child in self.rows.winfo_children():
            child.destroy()
        self.chips = {}
        measure = tkfont.Font(family=theme.FONT_TEXT, size=-12).measure
        row, used = None, self.WIDTH
        for label, color in [*tags, ("+ Tag mới", None)]:
            width = max(measure(label) + 26, 44)
            if used + width > self.WIDTH:
                row = ctk.CTkFrame(self.rows, fg_color="transparent")
                row.pack(fill="x")
                used = 0
            if color:
                chip = TagChip(row, label, color, lambda name=label: self._toggle(name), width=width)
                self.chips[label] = chip
            else:
                chip = Chip(row, label, self._show_entry, width=width)
            chip.pack(side="left", padx=(0, self.GAP), pady=(0, self.GAP))
            used += width + self.GAP

    def _toggle(self, name):
        if name in self.selected:
            self.selected.remove(name)
        else:
            self.selected.append(name)
        self.chips[name].set_active(name in self.selected)
        self.on_change(self.selected)

    def _show_entry(self):
        self.entry.pack(fill="x", pady=(0, 4))
        self.entry.focus_set()

    def _hide_entry(self):
        set_text(self.entry, "")
        self.entry.pack_forget()

    def _add(self, _event=None):
        name = self.entry.get().strip().lstrip("#")
        if tag_key(name):
            self.app.store.ensure_tag(name)
            label = self.app.store.tag_label(name)
            if label not in self.selected:
                self.selected.append(label)
            self._hide_entry()
            self.set_selected(self.selected)
            self.on_change(self.selected)
        return "break"


def group_entries(tasks, now, view):
    """Chia task thành các nhóm có tiêu đề, trả về danh sách dòng cho TaskList."""
    today = now.date()
    if view == "done":
        groups = {}
        for task in tasks:
            groups.setdefault(day_label(from_text(task["done_at"]).date(), today), []).append(task)
        return _flatten((name, MUTED, items) for name, items in groups.items())
    overdue, current, tomorrow, week, later, undated = [], [], [], [], [], []
    for task in tasks:
        if not task["due_at"]:
            undated.append(task)
            continue
        due = from_text(task["due_at"])
        gap = (due.date() - today).days
        if due < now:
            overdue.append(task)
        elif gap == 0:
            current.append(task)
        elif gap == 1:
            tomorrow.append(task)
        elif gap < 7:
            week.append(task)
        else:
            later.append(task)
    return _flatten((("Quá hạn", RED, overdue), ("Hôm nay", ACCENT, current), ("Ngày mai", MUTED, tomorrow),
                     ("7 ngày tới", MUTED, week), ("Sau này", MUTED, later), ("Chưa có hạn", MUTED, undated)))


def _flatten(groups):
    entries = []
    for name, color, items in groups:
        if items:
            entries.append(("header", name, len(items), color))
            entries.extend(("task", item) for item in items)
    return entries


class TaskList(ctk.CTkFrame):
    """Danh sách ảo: chỉ vẽ những dòng đang nhìn thấy, 10 hay 10.000 task đều mượt như nhau."""
    ROW, HEADER, CHECK_WIDTH = 58, 32, 44
    FONTS = {"title": ("FONT_TEXT", 14, 0), "done": ("FONT_TEXT", 14, 1), "meta": ("FONT_TEXT", 12, 0),
             "header": ("FONT_SEMIBOLD", 12, 0), "check": ("FONT_ICON", 20, 0), "glyph": ("FONT_ICON", 11, 0),
             "dot": ("FONT_ICON", 8, 0)}

    def __init__(self, master, app, on_select, on_open=None, empty_text="Không có việc nào ở đây"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.on_toggle, self.on_select, self.on_open = app.toggle_task, on_select, on_open
        self.empty_text = empty_text
        self.entries, self.tops = [], []
        self.total = 0
        self.offset = 0
        self.hover_index = None
        self.hover_check = False
        self.selected_id = None
        self.scale = 1.0
        self.fonts = FontCache(self.FONTS)
        self.draw_pending = False

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=resolve(CARD), takefocus=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ctk.CTkScrollbar(self, command=self._on_scrollbar, width=12, fg_color="transparent",
                                          button_color=TRACK, button_hover_color=MUTED)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.scrollbar.grid_remove()

        canvas = self.canvas
        canvas.bind("<Configure>", lambda _: self._schedule_draw())
        canvas.bind("<Motion>", self._on_motion)
        canvas.bind("<Leave>", lambda _: self._set_hover(None, False))
        canvas.bind("<Button-1>", self._on_click)
        canvas.bind("<Double-Button-1>", self._on_double_click)
        canvas.bind("<MouseWheel>", lambda event: self._scroll_by(-event.delta / 120 * self.ROW * self.scale))
        canvas.bind("<Up>", lambda _: self._move_selection(-1))
        canvas.bind("<Down>", lambda _: self._move_selection(1))
        canvas.bind("<space>", lambda _: self._toggle_selected())
        AppearanceModeTracker.add(lambda _mode: self._on_theme(), self)

    # ---------- Dữ liệu ----------

    def set_entries(self, entries):
        self.entries = entries
        self._layout()
        self._schedule_draw()

    def select(self, task_id):
        self.selected_id = task_id
        self._schedule_draw()

    def task_ids(self):
        return [entry[1]["id"] for entry in self.entries if entry[0] == "task"]

    def _layout(self):
        self.scale = ScalingTracker.get_widget_scaling(self)
        self.fonts.rescale(self.scale)
        self.tops = []
        position = 0
        for entry in self.entries:
            self.tops.append(position)
            position += round((self.ROW if entry[0] == "task" else self.HEADER) * self.scale)
        self.total = position
        self.offset = max(min(self.offset, self.total - self.canvas.winfo_height()), 0)

    def _on_theme(self):
        self.canvas.configure(bg=resolve(CARD))
        self._schedule_draw()

    # ---------- Vẽ ----------

    def _schedule_draw(self):
        if not self.draw_pending:
            self.draw_pending = True
            self.after_idle(self._paint)

    def _paint(self):
        self.draw_pending = False
        if not self.winfo_exists():
            return
        canvas = self.canvas
        canvas.delete("all")
        if ScalingTracker.get_widget_scaling(self) != self.scale:
            self._layout()
        width, height = canvas.winfo_width(), canvas.winfo_height()
        self._sync_scrollbar(height)
        if not self.entries:
            canvas.create_text(width / 2, height / 2, text=self.empty_text, fill=resolve(MUTED), justify="center",
                               width=max(width - 60, 100), font=self.fonts.get("title"))
            return
        now = datetime.now()
        index = max(bisect_right(self.tops, self.offset) - 1, 0)
        while index < len(self.entries) and self.tops[index] - self.offset < height:
            top = self.tops[index] - self.offset
            entry = self.entries[index]
            if entry[0] == "header":
                self._draw_header(entry, top)
            else:
                self._draw_task(entry[1], top, width, now, index == self.hover_index)
            index += 1

    def _draw_header(self, entry, top):
        _, name, count, color = entry
        middle = top + round(self.HEADER * self.scale * 0.58)
        left = round(8 * self.scale)
        self.canvas.create_text(left, middle, text=name, anchor="w", font=self.fonts.get("header"), fill=resolve(color))
        self.canvas.create_text(left + self.fonts.measure("header", name) + round(6 * self.scale), middle, text=str(count),
                                anchor="w", font=self.fonts.get("meta"), fill=resolve(MUTED))

    def _draw_task(self, task, top, width, now, hovered):
        canvas, scale = self.canvas, self.scale
        height = round(self.ROW * scale)
        selected = task["id"] == self.selected_id
        if selected or hovered:
            canvas.create_rectangle(0, top, width, top + height - 1, outline="",
                                    fill=resolve(ACCENT_SOFT if selected else CARD_HOVER))
        if selected:
            canvas.create_rectangle(0, top, round(3 * scale), top + height - 1, outline="", fill=resolve(ACCENT))
        check_x = round(23 * scale)
        middle = top + height // 2
        done = bool(task["done_at"])
        glyph, color = (Icon.DONE, GREEN) if done else (Icon.RING, theme.PRIORITY_COLORS[task["priority"]])
        if hovered and self.hover_check and not done:
            glyph, color = Icon.DONE, GREEN
        canvas.create_text(check_x, middle, text=glyph, font=self.fonts.get("check"), fill=resolve(color))
        left = round(self.CHECK_WIDTH * scale)
        room = width - left - round(14 * scale)
        font = "done" if done else "title"
        canvas.create_text(left, top + round(20 * scale), text=self.fonts.fit(font, task["title"], room), anchor="w",
                           font=self.fonts.get(font), fill=resolve(MUTED if done else TEXT))
        self._draw_meta(task, left, top + round(41 * scale), left + room, now)

    def _meta_parts(self, task, now):
        """Các mảnh của dòng phụ: (icon, chữ, màu chữ, màu icon)."""
        parts = []
        if task["done_at"]:
            parts.append((None, f"Xong lúc {task['done_at'][11:16]}", MUTED, MUTED))
        elif task["due_at"]:
            due = from_text(task["due_at"])
            label, color = when_label(task["due_at"], task["all_day"], now), MUTED
            label = {"Hôm nay": "Cả ngày"}.get(label, label.removeprefix("Hôm nay "))
            if due < now:
                label, color = f"{label} · trễ {humanize(now - due)}", RED
            elif due - now < timedelta(hours=1):
                label, color = f"{label} · còn {humanize(due - now)}", AMBER
            parts.append((Icon.CLOCK, label, color, color))
        window = block_window(task)
        if window and not task["done_at"]:
            start, end = window
            if start <= now < end:
                parts.append((Icon.TIMER, f"Đang chạy · còn {humanize(end - now)}", ACCENT, ACCENT))
            elif end > now:
                parts.append((Icon.TIMER, f"{start:%H:%M}–{end:%H:%M}", MUTED, MUTED))
        if task["recur"]:
            parts.append((Icon.REPEAT, "", MUTED, MUTED))
        for name in task_tag_names(task):
            parts.append((Icon.DOT, name, MUTED, tag_edge(self.app.tag_color(name))))
        return parts

    def _draw_meta(self, task, x, y, limit, now):
        canvas, scale = self.canvas, self.scale
        gap = round(12 * scale)
        for glyph, label, color, glyph_color in self._meta_parts(task, now):
            if glyph:
                font = "dot" if glyph == Icon.DOT else "glyph"
                canvas.create_text(x, y, text=glyph, anchor="w", font=self.fonts.get(font), fill=resolve(glyph_color))
                x += self.fonts.measure(font, glyph) + round(4 * scale)
            if label:
                label = self.fonts.fit("meta", label, limit - x)
                canvas.create_text(x, y, text=label, anchor="w", font=self.fonts.get("meta"), fill=resolve(color))
                x += self.fonts.measure("meta", label)
            x += gap
            if x >= limit:
                return
        total = task["cp_total"]
        if total and x + round(70 * scale) < limit:
            bar, thickness = round(44 * scale), max(round(4 * scale), 2)
            top = y - thickness // 2
            canvas.create_rectangle(x, top, x + bar, top + thickness, outline="", fill=resolve(TRACK))
            filled = round(bar * task["cp_done"] / total)
            if filled:
                canvas.create_rectangle(x, top, x + filled, top + thickness, outline="",
                                        fill=resolve(GREEN if filled == bar else ACCENT))
            canvas.create_text(x + bar + round(6 * scale), y, text=f"{task['cp_done']}/{total}", anchor="w",
                               font=self.fonts.get("meta"), fill=resolve(MUTED))

    # ---------- Cuộn và tương tác ----------

    def _sync_scrollbar(self, height):
        if self.total <= height:
            self.scrollbar.grid_remove()
            self.offset = 0
        else:
            self.scrollbar.grid()
            self.scrollbar.set(self.offset / self.total, (self.offset + height) / self.total)

    def _scroll_to(self, offset):
        limit = max(self.total - self.canvas.winfo_height(), 0)
        offset = max(min(offset, limit), 0)
        if offset != self.offset:
            self.offset = offset
            self._schedule_draw()

    def _scroll_by(self, amount):
        self._scroll_to(self.offset + amount)

    def _on_scrollbar(self, action, value, unit=None):
        if action == "moveto":
            self._scroll_to(float(value) * self.total)
        elif action == "scroll":
            self._scroll_by(int(value) * self.ROW * self.scale)

    def _index_at(self, y):
        if not self.entries:
            return None
        position = y + self.offset
        index = bisect_right(self.tops, position) - 1
        return index if 0 <= index and position < self.total else None

    def _set_hover(self, index, on_check):
        if index != self.hover_index or on_check != self.hover_check:
            self.hover_index = index
            self.hover_check = on_check
            self._schedule_draw()

    def _on_motion(self, event):
        index = self._index_at(event.y)
        is_task = index is not None and self.entries[index][0] == "task"
        self._set_hover(index if is_task else None, is_task and event.x < self.CHECK_WIDTH * self.scale)

    def _on_click(self, event):
        self.canvas.focus_set()
        index = self._index_at(event.y)
        if index is None or self.entries[index][0] != "task":
            return
        task = self.entries[index][1]
        if event.x < self.CHECK_WIDTH * self.scale:
            self.on_toggle(task)
        else:
            self.select(task["id"])
            self.on_select(task["id"])

    def _on_double_click(self, event):
        index = self._index_at(event.y)
        if self.on_open and index is not None and self.entries[index][0] == "task" and event.x >= self.CHECK_WIDTH * self.scale:
            self.on_open(self.entries[index][1]["id"])

    def _move_selection(self, step):
        ids = self.task_ids()
        if not ids:
            return "break"
        position = ids.index(self.selected_id) + step if self.selected_id in ids else 0
        task_id = ids[max(min(position, len(ids) - 1), 0)]
        self.select(task_id)
        self.on_select(task_id)
        self._reveal(task_id)
        return "break"

    def _reveal(self, task_id):
        for index, entry in enumerate(self.entries):
            if entry[0] == "task" and entry[1]["id"] == task_id:
                top, bottom = self.tops[index], self.tops[index] + round(self.ROW * self.scale)
                height = self.canvas.winfo_height()
                if top < self.offset:
                    self._scroll_to(top)
                elif bottom > self.offset + height:
                    self._scroll_to(bottom - height)
                return

    def _toggle_selected(self):
        for entry in self.entries:
            if entry[0] == "task" and entry[1]["id"] == self.selected_id:
                self.on_toggle(entry[1])
                break
        return "break"


class WeekChart(tk.Canvas):
    """Biểu đồ cột 7 ngày."""

    def __init__(self, master):
        super().__init__(master, highlightthickness=0, bd=0, height=64, bg=resolve(CARD))
        self.week = []
        self.bind("<Configure>", lambda _: self._draw())
        AppearanceModeTracker.add(lambda _mode: self._on_theme(), self)

    def _on_theme(self):
        self.configure(bg=resolve(CARD))
        self._draw()

    def set_week(self, week):
        if week != self.week:
            self.week = week
            self._draw()

    def _draw(self):
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if not self.week or width < 20:
            return
        scale = ScalingTracker.get_widget_scaling(self)
        label_height = round(15 * scale)
        peak = max(max(count for _, count in self.week), 1)
        slot = width / 7
        bar = min(slot * 0.56, 26 * scale)
        room = height - label_height - round(2 * scale)
        small = (theme.FONT_TEXT, -round(10 * scale))
        for index, (day, count) in enumerate(self.week):
            x = slot * index + slot / 2
            is_today = index == len(self.week) - 1
            size = max(round(room * count / peak), round(2 * scale))
            self.create_rectangle(x - bar / 2, room - size, x + bar / 2, room, outline="",
                                  fill=resolve((ACCENT if is_today else CHART_BAR) if count else TRACK))
            self.create_text(x, height - label_height / 2, text=WEEKDAY_SHORT[day.weekday()], font=small,
                             fill=resolve(TEXT if is_today else MUTED))


class DatePicker(tk.Toplevel):
    """Lịch tháng dạng popup, vẽ trên một Canvas."""
    COLUMNS, ROWS, CELL = 7, 8, 36

    def __init__(self, anchor, current, on_pick):
        super().__init__(anchor)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.on_pick = on_pick
        self.today = date.today()
        self.current = current
        self.year, self.month = (current or self.today).year, (current or self.today).month
        self.scale = ScalingTracker.get_widget_scaling(anchor)
        self.cell = round(self.CELL * self.scale)
        size = (self.cell * self.COLUMNS, self.cell * self.ROWS)
        self.canvas = tk.Canvas(self, width=size[0], height=size[1], highlightthickness=0, bd=0, bg=resolve(CARD))
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_click)
        self.bind("<Escape>", lambda _: self.destroy())
        self.bind("<FocusOut>", lambda _: self.destroy())
        x = min(anchor.winfo_rootx(), anchor.winfo_screenwidth() - size[0] - 8)
        y = anchor.winfo_rooty() + anchor.winfo_height() + 4
        if y + size[1] > anchor.winfo_screenheight() - 48:
            y = anchor.winfo_rooty() - size[1] - 4
        self.geometry(f"{size[0]}x{size[1]}+{x}+{y}")
        self._draw()
        self.deiconify()
        self.update_idletasks()
        set_window_rounded(self.winfo_id())
        self.focus_force()

    def _font(self, size, semibold=False):
        return (theme.FONT_SEMIBOLD if semibold else theme.FONT_TEXT, -round(size * self.scale))

    def _draw(self):
        canvas, cell = self.canvas, self.cell
        canvas.delete("all")
        canvas.create_text(self.COLUMNS * cell / 2, cell / 2, text=f"Tháng {self.month}, {self.year}",
                           font=self._font(14, True), fill=resolve(TEXT))
        glyph = (theme.FONT_ICON, -round(12 * self.scale))
        canvas.create_text(cell / 2, cell / 2, text=Icon.LEFT, font=glyph, fill=resolve(MUTED))
        canvas.create_text(cell * 6.5, cell / 2, text=Icon.RIGHT, font=glyph, fill=resolve(MUTED))
        for column, name in enumerate(WEEKDAY_SHORT):
            canvas.create_text(cell * (column + 0.5), cell * 1.5, text=name, font=self._font(11), fill=resolve(MUTED))
        for row, week in enumerate(calendar.Calendar().monthdayscalendar(self.year, self.month)):
            for column, number in enumerate(week):
                if number:
                    self._draw_day(number, column, row + 2)

    def _draw_day(self, number, column, row):
        canvas, cell = self.canvas, self.cell
        day = date(self.year, self.month, number)
        x, y = cell * column, cell * row
        inset = round(3 * self.scale)
        color = TEXT
        if day == self.current:
            canvas.create_rectangle(x + inset, y + inset, x + cell - inset, y + cell - inset, outline="", fill=resolve(FILL))
            color = ON_FILL
        elif day == self.today:
            canvas.create_rectangle(x + inset, y + inset, x + cell - inset, y + cell - inset, outline="", fill=resolve(ACCENT_SOFT))
            color = ACCENT
        canvas.create_text(x + cell / 2, y + cell / 2, text=str(number), font=self._font(13), fill=resolve(color))

    def _step(self, months):
        index = self.year * 12 + self.month - 1 + months
        self.year, self.month = index // 12, index % 12 + 1
        self._draw()

    def _on_click(self, event):
        column, row = int(event.x // self.cell), int(event.y // self.cell)
        if row == 0:
            if column == 0:
                self._step(-1)
            elif column == self.COLUMNS - 1:
                self._step(1)
            return
        weeks = calendar.Calendar().monthdayscalendar(self.year, self.month)
        if row >= 2 and row - 2 < len(weeks) and weeks[row - 2][column]:
            picked = date(self.year, self.month, weeks[row - 2][column])
            self.destroy()
            self.on_pick(picked)


class Snackbar(ctk.CTkFrame):
    """Thông báo ngắn trong app, có nút hoàn tác."""

    def __init__(self, master):
        super().__init__(master, fg_color=FILL, corner_radius=10, height=44)
        self.label = ctk.CTkLabel(self, text="", font=theme.text(13), text_color=ON_FILL)
        self.label.pack(side="left", padx=(16, 10), pady=6)
        self.button = ctk.CTkButton(self, text="", width=70, height=28, corner_radius=6, fg_color="transparent",
                                    hover_color=FILL_HOVER, text_color=ON_FILL, font=theme.semibold(13), command=self._run)
        self.button.pack(side="left", padx=(0, 8))
        self.action = None
        self.timer = None

    def show(self, message, action_label=None, action=None):
        if self.timer:
            self.after_cancel(self.timer)
        self.action = action
        self.label.configure(text=message if len(message) <= 60 else message[:59] + "…")
        if action_label:
            self.button.configure(text=action_label)
            self.button.pack(side="left", padx=(0, 8))
        else:
            self.button.pack_forget()
        self.place(relx=0.5, rely=1.0, y=-20, anchor="s")
        self.lift()
        self.timer = self.after(5000, self.hide)

    def hide(self):
        self.timer = None
        self.place_forget()

    def _run(self):
        action = self.action
        self.hide()
        if action:
            action()
