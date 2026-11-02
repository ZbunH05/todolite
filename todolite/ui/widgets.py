"""Các widget tự vẽ. Mọi thứ dài/lặp lại đều nằm trên một Canvas duy nhất, vì mỗi widget
CustomTkinter là cả một cụm widget Tk: 300 dòng task dựng bằng CTk sẽ ngốn RAM và giật khi cuộn.
"""
import calendar
import tkinter as tk
import tkinter.font as tkfont
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta

import customtkinter as ctk
from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import AppearanceModeTracker
from customtkinter.windows.widgets.core_widget_classes import CTkBaseClass
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from ..daybook import hours_of
from ..db import tag_key, task_tag_names
from ..quickparse import describe, parse, tag_prefix
from ..schedule import SHOWS_ALL, WEEKDAY_SHORT, TaskGroup, block_label, block_window, from_text, group_done, group_tasks, humanize, row_when
from ..win32 import set_window_rounded
from . import motion, theme
from .shapes import rounded
from .textfit import button_shape, button_text_top, fit_parts, fit_text
from .theme import (ACCENT, ACCENT_SOFT, AMBER, BG, BORDER, CARD, CARD_HOVER, CHART_BAR, FIELD, FILL, FILL_HOVER, GREEN, GREEN_EDGE, GREEN_SOFT,
                    GREEN_SOFT_HOVER, Icon, MUTED, ON_FILL, RED, RED_EDGE, RED_SOFT, RED_SOFT_HOVER, SEGMENT_SELECTED, TEXT, TRACK, blend, resolve,
                    tag_edge, tag_tint)

_ctk_grid = CTkBaseClass.grid


def _grid_remove(self):
    """CustomTkinter ghi nhớ lần grid cuối và gọi lại mỗi khi đổi tỉ lệ, kể cả với widget đã grid_remove, vì nó không ghi đè
    grid_remove. Không vá thì đổi Cỡ chữ làm mọi trang và panel đang ẩn hiện lại chồng lên trang đang mở."""
    if self._last_geometry_manager_call is not None:  # ẩn lần nữa khi đã ẩn thì giữ chỗ cũ, không xoá mất
        self._hidden_grid = self._last_geometry_manager_call
    self._last_geometry_manager_call = None
    tk.Grid.grid_remove(self)


def _grid(self, **kwargs):
    hidden = self.__dict__.pop("_hidden_grid", None)
    if not kwargs and hidden:
        kwargs = hidden["kwargs"]  # hiện lại đúng chỗ cũ, khoảng cách tính theo tỉ lệ hiện tại
    return _ctk_grid(self, **kwargs)


CTkBaseClass.grid_remove, CTkBaseClass.grid = _grid_remove, _grid

QUICK_HINT = "Gõ tự nhiên: mai 9h · t6 14:00 · 15/11 · hằng tuần · !1 ưu tiên · #học-tập · ~50p khối giờ"
_measure_fonts = {}


class Plain(ctk.CTkFrame):
    """Khung xếp chỗ, trong suốt. CTkFrame có một canvas riêng và vẽ lại hình bo góc mỗi lần đổi cỡ, ở đây không có gì để vẽ."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._canvas.place_forget()
        self._draw()

    def _draw(self, no_color_updates=False):
        if not no_color_updates:
            tk.Frame.configure(self, bg=self._apply_appearance_mode(self._bg_color))

    def bind(self, sequence=None, command=None, add=True):
        return tk.Frame.bind(self, sequence, command, add)


def _color(value):
    return value if isinstance(value, str) else resolve(value)


def scaled(value, scale):
    """Nhân theo tỉ lệ đúng như CustomTkinter: số nguyên bị cắt phần lẻ, số thực để Tk tự làm tròn. Lệch quy tắc này là lệch
    một điểm ảnh so với widget CustomTkinter đứng cạnh."""
    return int(value * scale) if isinstance(value, int) else value * scale


def _whole(value):
    return value if isinstance(value, int) else round(value)


class Scaled:
    """Xếp chỗ cho widget Tk thuần như widget CustomTkinter: padx, pady, x, y nhân theo Cỡ chữ và được tính lại khi Cỡ chữ đổi."""
    _scale = 1.0
    _layout = None  # lệnh xếp chỗ cuối, gọi lại với khoảng cách mới khi đổi Cỡ chữ

    def _relayout(self):
        if self._layout and self.winfo_manager():
            self._layout[0](self, **self._scaled(self._layout[1]))

    def _scaled(self, options):
        result = dict(options)
        for key in ("padx", "pady", "x", "y"):
            if key in result:
                value = result[key]
                result[key] = tuple(scaled(part, self._scale) for part in value) if isinstance(value, tuple) else scaled(value, self._scale)
        return result

    def pack(self, **kwargs):
        self._layout = (tk.Pack.pack_configure, kwargs)
        tk.Pack.pack_configure(self, **self._scaled(kwargs))

    def grid(self, **kwargs):
        if not kwargs and self._layout and self._layout[0] is tk.Grid.grid_configure:
            kwargs = self._layout[1]  # hiện lại sau grid_remove, khoảng cách theo Cỡ chữ hiện tại
        self._layout = (tk.Grid.grid_configure, kwargs)
        tk.Grid.grid_configure(self, **self._scaled(kwargs))

    def place(self, **kwargs):
        self._layout = (tk.Place.place_configure, kwargs)
        tk.Place.place_configure(self, **self._scaled(kwargs))


class Label(Scaled, tk.Label):
    """Nhãn chữ một cửa sổ Tk, thay CTkLabel (khung, canvas và nhãn) ở mọi chỗ chữ không cần nền bo góc. Gọi giống CTkLabel:
    height và width là cỡ tối thiểu tính bằng điểm ảnh, màu là cặp (sáng, tối), font, cỡ và khoảng cách khi xếp đều nhân theo
    Cỡ chữ. Nền lấy theo khung cha như CTkLabel trong suốt."""
    _detect_color_of_master = CTkBaseClass._detect_color_of_master

    def __init__(self, master, text="", font=None, text_color=TEXT, height=28, width=0, wraplength=0, elastic=False, **kwargs):
        root = master._root()
        if not hasattr(root, "label_blank"):
            root.label_blank = tk.PhotoImage(width=1, height=1)  # có ảnh thì width/height tính bằng điểm ảnh thay vì số ký tự
        self._text, self._font, self._text_color = text, font or theme.text(13), text_color
        self._least, self._wraplength = (width, height), wraplength
        # elastic: nhãn xuống dòng theo bề rộng khung cha. Nó không được xin bề rộng theo chữ, kẻo xin rộng thêm 1 điểm ảnh làm
        # cột co lại, chữ xuống thêm một dòng nên xin hẹp đi, cột nở ra, và cứ thế lặp mãi: Tổng quan từng treo vì vòng này.
        self._elastic = elastic
        self._scale = ScalingTracker.get_widget_scaling(master)
        super().__init__(master, text=text, image=root.label_blank, compound="center", borderwidth=0, padx=0, pady=0,
                         highlightthickness=0, **kwargs)
        self._on_theme()
        self._rescale()
        AppearanceModeTracker.add(self._on_theme, self)
        ScalingTracker.add_widget(self._on_scaling, self)

    def destroy(self):
        AppearanceModeTracker.remove(self._on_theme)
        ScalingTracker.remove_widget(self._on_scaling, self)
        super().destroy()

    def _on_theme(self, _mode=None):
        tk.Label.configure(self, fg=_color(self._text_color), bg=_color(self._detect_color_of_master()))

    def _on_scaling(self, scale, _window=None):
        self._scale = scale
        self._rescale()
        self._relayout()

    def _rescale(self):
        tk.Label.configure(self, font=(self._font[0], -abs(round(self._font[1] * self._scale)), *self._font[2:]),
                           wraplength=scaled(self._wraplength, self._scale))
        self._fit()

    def _fit(self):
        """Đo cỡ tự nhiên của chữ rồi nâng lên cỡ tối thiểu, như khung CTkLabel ôm cả canvas lẫn nhãn."""
        tk.Label.configure(self, width=0, height=0)
        width, height = (_whole(scaled(value, self._scale)) for value in self._least)
        need = {}
        if self._elastic:
            need["width"] = max(width, 1)
        elif width > self.winfo_reqwidth():
            need["width"] = width
        if height > self.winfo_reqheight():
            need["height"] = height
        if need:
            tk.Label.configure(self, **need)

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs |= cnf
        fit = False
        if "text" in kwargs:
            self._text = kwargs["text"]
            fit = True
        if "text_color" in kwargs:
            self._text_color = kwargs.pop("text_color")
            self._on_theme()
        if "font" in kwargs:
            self._font = kwargs.pop("font")
            kwargs["font"] = (self._font[0], -abs(round(self._font[1] * self._scale)), *self._font[2:])
            fit = True
        if "wraplength" in kwargs:
            self._wraplength = kwargs["wraplength"]
            kwargs["wraplength"] = scaled(self._wraplength, self._scale)
            fit = True
        for index, key in enumerate(("width", "height")):
            if key in kwargs:
                least = list(self._least)
                least[index] = kwargs.pop(key)
                self._least = tuple(least)
                fit = True
        if kwargs:
            tk.Label.configure(self, **kwargs)
        if fit:
            self._fit()

    config = configure


class TextBox(ctk.CTkTextbox):
    """CTkTextbox không có thanh cuộn riêng. Bản gốc dò xem có cần thanh cuộn 5 lần/giây suốt đời widget, kể cả khi đã tắt
    thanh cuộn, và mỗi lần lại grid lại thanh cuộn: ba ô chữ là 15 lần thức mỗi giây khi app đứng yên."""

    def __init__(self, master, **kwargs):
        super().__init__(master, activate_scrollbars=False, **kwargs)

    def _check_if_scrollbars_needed(self, event=None, continue_loop=False):
        pass


class Card(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        options = dict(fg_color=CARD, corner_radius=theme.RADIUS_CARD, border_width=1, border_color=BORDER)
        super().__init__(master, **(options | kwargs))


class IconButton(ctk.CTkButton):
    def __init__(self, master, glyph, command, size=30, color=MUTED, hover=CARD_HOVER):
        super().__init__(master, text=glyph, command=command, width=size, height=size, corner_radius=theme.RADIUS_CONTROL,
                         fg_color="transparent", hover_color=hover, text_color=color, font=theme.icon(14))


class Chip(Scaled, tk.Canvas):
    """Nút nhỏ bật/tắt, bo tròn hẳn hai đầu. Một Canvas tự vẽ thay CTkButton (khung, canvas, nhãn): bảng sửa việc có gần
    hai chục chip, dựng nhanh gấp ba. Cỡ, vị trí chữ, màu khi rê chuột và lúc bấm giữ đúng như CTkButton cùng tham số."""
    HEIGHT = 26
    _detect_color_of_master = CTkBaseClass._detect_color_of_master

    def __init__(self, master, label, command, width=0):
        self._text, self._command, self._least = label, command, width or 44
        self.active = self._inside = self._hover = False
        self._flash = None
        self._scale = ScalingTracker.get_widget_scaling(master)
        super().__init__(master, highlightthickness=0, borderwidth=0, cursor="hand2")
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._rescale()
        AppearanceModeTracker.add(self._draw, self)
        ScalingTracker.add_widget(self._on_scaling, self)

    def destroy(self):
        AppearanceModeTracker.remove(self._draw)
        ScalingTracker.remove_widget(self._on_scaling, self)
        if self._flash:
            self.after_cancel(self._flash)
        super().destroy()

    def _on_scaling(self, scale, _window=None):
        self._scale = scale
        self._rescale()
        self._relayout()

    def _rescale(self):
        """Cỡ như lưới bên trong CTkButton: chữ cộng hai lề bằng bán kính góc, không nhỏ hơn cỡ đã xin."""
        scale = self._scale
        self._font = (theme.FONT_TEXT, -abs(round(12 * scale)))
        metrics = _measure_font(theme.text(12), scale)
        edge, line = _whole(scaled(2, scale)), metrics.metrics("linespace") + 2
        self._size = (max(_whole(scaled(self._least, scale)), 2 * _whole(scaled(self.HEIGHT // 2, scale)) + metrics.measure(self._text) + 2),
                      max(_whole(scaled(self.HEIGHT, scale)), 2 * edge + line))
        self._text_top = button_text_top(self._size[1], edge, line)
        self._shape = button_shape((self._least, self.HEIGHT), self._size, scale)
        tk.Canvas.configure(self, width=self._size[0], height=self._size[1])
        self._draw()

    def _draw(self, _mode=None):
        style = self._style(self.active)
        back = _color(self._detect_color_of_master())
        inner = style["hover_color"] if self._hover else style["fg_color"]
        inner = back if inner == "transparent" else _color(inner)
        width, height = self._shape
        self.delete("all")
        tk.Canvas.configure(self, bg=back)
        rounded(self, 0, 0, width, height, scaled(self.HEIGHT // 2, self._scale), inner, back, _color(style["border_color"]),
                max(1, round(self._scale)))
        self._draw_label(_color(style["text_color"]))

    def _draw_label(self, color):
        self.create_text(self._size[0] // 2, self._text_top, text=self._text, font=self._font, fill=color, anchor="n")

    def _on_enter(self, _event=None):
        self._inside = self._hover = True
        self._draw()

    def _on_leave(self, _event=None):
        self._inside = self._hover = False
        self._draw()

    def _on_release(self, _event=None):
        if self._inside:  # như CTkButton: nhả chuột bên trong mới tính, màu rê chuột tắt 100 ms cho thấy đã bấm
            self._hover = False
            self._draw()
            self._flash = self.after(100, self._end_flash)
            self.invoke()

    def _end_flash(self):
        self._flash = None
        self._hover = self._inside
        self._draw()

    def invoke(self):
        return self._command() if self._command else None

    def set_active(self, active):
        if active != self.active:
            self.active = active
            self._draw()

    def _style(self, active):
        return dict(fg_color=ACCENT_SOFT if active else "transparent", hover_color=ACCENT_SOFT if active else CARD_HOVER,
                    text_color=TEXT if active else MUTED, border_color=ACCENT if active else BORDER)


class GlyphChip(Chip):
    """Chip mang một icon Segoe Fluent đặt giữa, như nút bớt, thêm thời lượng: dấu - + của font chữ ở cỡ 12 nhỏ như dấu chấm."""
    GLYPH = 10

    def _draw_label(self, color):
        font = (theme.FONT_ICON, -abs(round(self.GLYPH * self._scale)))
        self.create_text(self._shape[0] / 2, self._shape[1] / 2, text=self._text, font=font, fill=color, anchor="center")


class TagChip(Chip):
    """Chip mang màu của tag: viền màu khi chưa chọn, nền màu khi đã chọn."""

    def __init__(self, master, label, color, command, width=0):
        self.tag_color = color
        super().__init__(master, label, command, width)

    def _style(self, active):
        tint, edge = tag_tint(self.tag_color), tag_edge(self.tag_color)
        return dict(fg_color=tint if active else "transparent", hover_color=tint, text_color=TEXT if active else MUTED,
                    border_color=edge if active else (blend(edge[0], CARD[0], 0.45), blend(edge[1], CARD[1], 0.45)))


def primary_button(master, label, command, **kwargs):
    options = dict(height=32, corner_radius=theme.RADIUS_CONTROL, fg_color=FILL, hover_color=FILL_HOVER, text_color=ON_FILL,
                   font=theme.semibold(13))
    return ctk.CTkButton(master, text=label, command=command, **(options | kwargs))


def secondary_button(master, label, command, **kwargs):
    options = dict(height=32, corner_radius=theme.RADIUS_CONTROL, fg_color="transparent", hover_color=CARD_HOVER, text_color=TEXT,
                   border_width=1, border_color=BORDER, font=theme.text(13))
    return ctk.CTkButton(master, text=label, command=command, **(options | kwargs))


def segmented(master, values, command, **kwargs):
    options = dict(height=30, corner_radius=theme.RADIUS_CONTROL, font=theme.text(12), selected_color=SEGMENT_SELECTED,
                   selected_hover_color=SEGMENT_SELECTED, unselected_color=FIELD, fg_color=FIELD,
                   unselected_hover_color=CARD_HOVER, text_color=TEXT)
    return ctk.CTkSegmentedButton(master, values=values, command=command, **(options | kwargs))


def field(master, **kwargs):
    options = dict(height=34, corner_radius=theme.RADIUS_CONTROL, border_width=1, border_color=BORDER, fg_color=FIELD, text_color=TEXT,
                   placeholder_text_color=MUTED, font=theme.text(13))
    entry = ctk.CTkEntry(master, **(options | kwargs))
    entry.bind("<FocusIn>", lambda _: entry.configure(border_color=ACCENT))
    entry.bind("<FocusOut>", lambda _: entry.configure(border_color=BORDER))
    return entry


def set_label(label, **options):
    """Chỉ configure khi giá trị khác lần trước: CTkLabel vẽ lại cả canvas mỗi lần, dù chữ không đổi."""
    shown = label.__dict__.setdefault("shown_options", {})
    changed = {key: value for key, value in options.items() if shown.get(key) != value}
    if changed:
        shown.update(changed)
        label.configure(**changed)


def set_text(entry, value):
    """Gán nội dung ô nhập. CTkEntry coi ô mới tạo là đang focus nên sẽ không hiện lại
    placeholder sau khi xoá, phải báo trạng thái focus thật cho nó trước."""
    entry._is_focused = entry.focus_get() is entry._entry
    entry.delete(0, "end")
    if value:
        entry.insert(0, value)


def _measure_font(font, scale):
    key = (font[0], round(font[1] * scale))
    if key not in _measure_fonts:
        _measure_fonts[key] = tkfont.Font(family=key[0], size=-key[1])
    return _measure_fonts[key]


def measure_text(font, scale, content):
    """Bề rộng tính bằng điểm ảnh thật của đoạn chữ với font dạng (họ, cỡ) sau khi nhân hệ số."""
    return _measure_font(font, scale).measure(content)


class FitLabel(Label):
    """Nhãn một dòng luôn nằm gọn trong bề rộng được cấp, không bao giờ bị cắt ngang chữ.

    Có separator thì bỏ dần các ý cuối, không thì thay phần thừa bằng dấu ba chấm. Phải xếp với fill="x",
    vì bề rộng phải do khung cha quyết định chứ không do chữ.
    """

    def __init__(self, master, text="", separator=None, **kwargs):
        self.full_text = text
        self.separator = separator
        super().__init__(master, text=text, **kwargs)
        self.bind("<Configure>", self._refit, add="+")

    def set_text(self, text):
        if text != self.full_text:
            self.full_text = text
            self._refit()

    def _refit(self, _event=None):
        room = self.winfo_width()
        shown = self.full_text if room <= 1 else self._fitted(room)
        if shown != self._text:
            self.configure(text=shown)

    def _fitted(self, room):
        scale = self._scale
        measure = lambda content: measure_text(self._font, scale, content)  # noqa: E731
        if self.separator:
            return fit_parts(measure, self.full_text, room, self.separator)
        return fit_text(measure, self.full_text, room)


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
        return fit_text(lambda piece: self.measure(name, piece), content, width)


class QuickEntry(Plain):
    """Ô thêm việc bằng câu tự nhiên, xem trước phần đã hiểu ngay khi gõ."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.entry = field(self, height=40, placeholder_text="Thêm việc mới…   (Ctrl+N)", font=theme.text(14))
        self.entry.pack(fill="x")
        self.entry.bind("<KeyRelease>", self._preview)
        self.entry.bind("<Return>", self._submit)
        self.entry.bind("<Tab>", self._complete_tag)
        self.preview = FitLabel(self, text=QUICK_HINT, separator=" · ", anchor="w", height=20, font=theme.text(12), text_color=MUTED)
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
            self.preview.set_text(f"{names}   ·   Tab để chọn")
            self.preview.configure(text_color=ACCENT)
            return
        summary = describe(parse(content), tag_label=self.app.store.tag_label) if content.strip() else ""
        self.preview.set_text(f"→  {summary}" if summary else QUICK_HINT)
        self.preview.configure(text_color=ACCENT if summary else MUTED)

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


class TagPicker(Plain):
    """Chọn nhiều tag bằng chip màu, tự xuống dòng; có thể tạo tag mới ngay tại chỗ."""
    WIDTH = 336
    GAP = 6

    def __init__(self, master, app, on_change):
        super().__init__(master)
        self.app = app
        self.on_change = on_change
        self.selected = []
        self.signature = None
        self.chips = {}
        ScalingTracker.add_widget(self._on_scaling, self)
        self.rows = Plain(self)
        self.rows.pack(fill="x")
        self.entry = field(self, height=30, placeholder_text="Tên tag mới, Enter để thêm")
        self.entry.bind("<Return>", self._add)
        self.entry.bind("<Escape>", lambda _: self._hide_entry())

    def _on_scaling(self, _scale, _window=None):
        """Chữ phóng to không đều theo từng cỡ nên phải xếp lại các chip. Để sau vòng lặp của ScalingTracker:
        xoá widget giữa vòng lặp làm danh sách của nó lệch đi và bỏ sót widget khác."""
        if self.signature is not None:
            self.signature = None
            self.after_idle(lambda: self.set_selected(self.selected))

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
        scale = ScalingTracker.get_widget_scaling(self)
        row, used = None, self.WIDTH
        for label, color in [*tags, ("+ Tag mới", None)]:
            width = max(measure_text(theme.text(12), scale, label) / scale + 30, 44)
            if used + width > self.WIDTH:
                row = Plain(self.rows)
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


GROUP_COLORS = {"late": RED, "today": ACCENT, "done": GREEN, "": MUTED}
# Thẻ việc quá hạn nền đỏ nhạt, việc đã xong nền xanh lá nhạt: (nền, nền khi rê chuột, viền, màu nhấn)
TILE_TONES = {"late": (RED_SOFT, RED_SOFT_HOVER, RED_EDGE, RED), "done": (GREEN_SOFT, GREEN_SOFT_HOVER, GREEN_EDGE, GREEN)}


def group_entries(tasks, now, view, done=()):
    """Danh sách dòng cho TaskList: tiêu đề nhóm, rồi các việc kèm cho biết dòng đó phải tự nói tới đâu. done là các việc đã
    xong hôm nay, xếp thành nhóm cuối để Tổng quan cho thấy cả phần đã làm được."""
    groups = group_done(tasks, now.date()) if view == "done" else group_tasks(tasks, now)
    if done:
        groups.append(TaskGroup("Đã xong hôm nay", "done", SHOWS_ALL, done))
    entries = []
    for group in groups:
        entries.append(("header", group.name, len(group.tasks), GROUP_COLORS[group.tone]))
        entries.extend(("task", task, group.shows) for task in group.tasks)
    return entries


class TaskList(Plain):
    """Danh sách ảo: chỉ vẽ những dòng đang nhìn thấy, 10 hay 10.000 task đều mượt như nhau.

    Mỗi việc là một thẻ bo góc riêng nằm trên nền trang. Mọi hình của một dòng mang chung tag row<số thứ tự> và tag rows.
    Khi cuộn, các dòng đã vẽ được giữ nguyên và chỉ dời đi bằng canvas.move; dòng lọt vào khung thì vẽ thêm, dòng ra khỏi khung thì xoá.
    """
    TILE, GAP, HEADER, CHECK_WIDTH = 62, 6, 34, 44
    ROW = TILE + GAP
    FONTS = {"title": ("FONT_TEXT", 14, 0), "done": ("FONT_TEXT", 14, 1), "meta": ("FONT_TEXT", 12, 0),
             "header": ("FONT_SEMIBOLD", 12, 0), "check": ("FONT_ICON", 20, 0), "glyph": ("FONT_ICON", 11, 0),
             "dot": ("FONT_ICON", 8, 0)}

    def __init__(self, master, app, on_select, on_open=None, empty_text="Không có việc nào ở đây"):
        super().__init__(master)
        self.app = app
        self.on_toggle, self.on_select, self.on_open = app.toggle_task, on_select, on_open
        self.empty_text = empty_text
        self.entries, self.tops = [], []
        self.index_of = {}  # id việc: số thứ tự dòng
        self.total = 0
        self.offset = 0  # số điểm ảnh đã cuộn, luôn là số nguyên để hình không nhoè
        self.live = range(0)  # các dòng đang có hình trên Canvas
        self.gutter = 0
        self.hover_index = None
        self.hover_check = False
        self.selected_id = None
        self.scale = 1.0
        self.fonts = FontCache(self.FONTS)
        self.draw_pending = False
        self.dirty = set()
        self.dirty_pending = False

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=resolve(BG), takefocus=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroller = motion.Scroller(self.canvas, lambda: self.offset, self._show_offset,
                                        lambda: (self.total, self.canvas.winfo_height()), self._on_settle)

        canvas = self.canvas
        canvas.bind("<Configure>", lambda _: self._schedule_draw())
        canvas.bind("<Motion>", self._on_motion)
        canvas.bind("<Leave>", lambda _: self._set_hover(None, False))
        canvas.bind("<Button-1>", self._on_click)
        canvas.bind("<Double-Button-1>", self._on_double_click)
        canvas.bind("<Up>", lambda _: self._move_selection(-1))
        canvas.bind("<Down>", lambda _: self._move_selection(1))
        canvas.bind("<space>", lambda _: self._toggle_selected())
        self.thumb = motion.Thumb(canvas, self.scroller, BG)  # sau các bind ở trên, vì bind không có add sẽ thay mất bind của con trượt
        AppearanceModeTracker.add(lambda _mode: self._on_theme(), self)

    # ---------- Dữ liệu ----------

    def set_entries(self, entries):
        self.entries = entries
        self._layout()
        self._schedule_draw()

    def select(self, task_id):
        """Chỉ vẽ lại dòng cũ và dòng mới."""
        previous, self.selected_id = self.selected_id, task_id
        if previous != task_id:
            self._schedule_rows(self.index_of.get(previous), self.index_of.get(task_id))

    def task_ids(self):
        return [entry[1]["id"] for entry in self.entries if entry[0] == "task"]

    def _layout(self):
        self.scale = ScalingTracker.get_widget_scaling(self)
        self.fonts.rescale(self.scale)
        self.tops = []
        self.index_of = {}
        position = 0
        tile = round(self.ROW * self.scale)
        header = round(self.HEADER * self.scale)
        for index, entry in enumerate(self.entries):
            self.tops.append(position)
            if entry[0] == "task":
                self.index_of[entry[1]["id"]] = index
                position += tile
            else:
                position += header
        self.total = position
        self.offset = max(min(self.offset, self.total - self.canvas.winfo_height()), 0)

    def _on_theme(self):
        self.canvas.configure(bg=resolve(BG))
        self._schedule_draw()

    def _view(self):
        height = self.canvas.winfo_height()
        return (self.offset / self.total, min((self.offset + height) / self.total, 1.0)) if self.total > height else (0.0, 1.0)

    def _visible(self):
        """Khoảng dòng giao với khung nhìn."""
        if not self.entries:
            return range(0)
        first = max(bisect_right(self.tops, self.offset) - 1, 0)
        return range(first, bisect_left(self.tops, self.offset + self.canvas.winfo_height()))

    def _row_width(self):
        return self.canvas.winfo_width() - self.gutter

    # ---------- Vẽ ----------

    def _schedule_draw(self):
        if not self.draw_pending:
            self.draw_pending = True
            self.after_idle(self._paint)

    def _schedule_rows(self, *indices):
        """Rê chuột chỉ đổi một hai dòng, không cần vẽ lại cả danh sách."""
        self.dirty.update(index for index in indices if index is not None)
        if self.dirty and not self.dirty_pending and not self.draw_pending:
            self.dirty_pending = True
            self.after_idle(self._paint_rows)

    def _paint(self):
        self.draw_pending = False
        self.dirty.clear()
        if not self.winfo_exists():
            return
        canvas = self.canvas
        if ScalingTracker.get_widget_scaling(self) != self.scale:
            self._layout()
        width, height = canvas.winfo_width(), canvas.winfo_height()
        scrollable = self.total > height
        self.offset = max(min(self.offset, self.total - height), 0)
        self.gutter = self.thumb.zone_width() if scrollable else 0  # con trượt nằm trên nền trang, không đè lên thẻ
        canvas.delete("all")
        self.thumb.forget()
        self.live = range(0)
        if not self.entries:
            canvas.create_text(width / 2, height / 2, text=self.empty_text, fill=resolve(MUTED), justify="center",
                               width=max(width - 60, 100), font=self.fonts.get("title"))
            self.thumb.update(0.0, 1.0)
            return
        now = datetime.now()
        self.live = self._visible()
        for index in self.live:
            self._draw_row(index, width - self.gutter, now)
        self.thumb.update(*self._view(), wake=False)

    def _paint_rows(self):
        self.dirty_pending = False
        rows, self.dirty = self.dirty, set()
        if self.draw_pending or not self.winfo_exists():
            return
        canvas = self.canvas
        width = self._row_width()
        now = datetime.now()
        for index in rows:
            canvas.delete(f"row{index}")
            if index in self.live:
                self._draw_row(index, width, now)

    def _draw_row(self, index, width, now):
        """Vẽ một dòng tại vị trí hiện tại của nó."""
        entry = self.entries[index]
        top, tag = self.tops[index] - self.offset, (f"row{index}", "rows")
        if entry[0] == "header":
            self._draw_header(entry, top, tag)
        else:
            self._draw_task(entry[1], entry[2], top, width, now, index == self.hover_index, tag)

    def _draw_header(self, entry, top, tag):
        _, name, count, color = entry
        middle = top + round(self.HEADER * self.scale * 0.6)
        left = round(4 * self.scale)
        self.canvas.create_text(left, middle, text=name, anchor="w", font=self.fonts.get("header"), fill=resolve(color), tags=tag)
        self.canvas.create_text(left + self.fonts.measure("header", name) + round(6 * self.scale), middle, text=str(count),
                                anchor="w", font=self.fonts.get("meta"), fill=resolve(MUTED), tags=tag)

    @staticmethod
    def _tone(task, now):
        if task["done_at"]:
            return "done"
        return "late" if task["due_at"] and from_text(task["due_at"]) < now else ""

    def _draw_task(self, task, shows, top, width, now, hovered, tag):
        canvas, scale = self.canvas, self.scale
        height = round(self.TILE * scale)
        selected = task["id"] == self.selected_id
        tone = TILE_TONES.get(self._tone(task, now))
        if selected:
            fill, edge = ACCENT_SOFT, ACCENT
        elif tone:
            fill, edge = tone[1] if hovered else tone[0], tone[2]
        else:
            fill, edge = CARD_HOVER if hovered else CARD, BORDER
        fill = resolve(fill)
        rounded(canvas, 0, top, width, top + height, round(theme.RADIUS_CARD * scale), fill, resolve(BG), outline=resolve(edge), tags=tag)
        done = bool(task["done_at"])
        glyph, color = (Icon.DONE, GREEN) if done else (Icon.RING, tone[3] if tone else theme.PRIORITY_COLORS[task["priority"]])
        if hovered and self.hover_check and not done:
            glyph, color = Icon.DONE, GREEN
        canvas.create_text(round(23 * scale), top + height // 2, text=glyph, font=self.fonts.get("check"), fill=resolve(color), tags=tag)
        left = round(self.CHECK_WIDTH * scale)
        room = width - left - round(14 * scale)
        parts = self._meta_parts(task, shows, now)
        font = "done" if done else "title"
        title_y = top + round(21 * scale) if parts or task["cp_total"] else top + height // 2  # không có dòng phụ thì tên việc nằm giữa thẻ
        canvas.create_text(left, title_y, text=self.fonts.fit(font, task["title"], room), anchor="w", font=self.fonts.get(font),
                           fill=resolve(GREEN if done else TEXT), tags=tag)
        self._draw_meta(task, parts, left, top + round(42 * scale), left + room, fill, tag)

    def _meta_parts(self, task, shows, now):
        """Các mảnh của dòng phụ: (icon, chữ, màu chữ, màu icon)."""
        parts = []
        if task["done_at"]:
            parts.append((None, f"Xong lúc {task['done_at'][11:16]}", MUTED, MUTED))
        elif task["due_at"]:
            due = from_text(task["due_at"])
            label, urgency, color = row_when(task, shows, now), "", MUTED
            if due < now:
                urgency, color = f"trễ {humanize(now - due)}", RED
            elif due - now < timedelta(hours=1):
                urgency, color = f"còn {humanize(due - now)}", AMBER
            label = " · ".join(piece for piece in (label, urgency) if piece)
            if label:
                parts.append((Icon.CLOCK, label, color, color))
        window = block_window(task)
        if window and not task["done_at"]:
            start, end = window
            if start <= now < end:
                parts.append((Icon.TIMER, f"Đang chạy · còn {humanize(end - now)}", ACCENT, ACCENT))
            elif end > now:
                parts.append((Icon.TIMER, block_label(task, now), MUTED, MUTED))
        if task["recur"]:
            parts.append((Icon.REPEAT, "", MUTED, MUTED))
        for name in task_tag_names(task):
            parts.append((Icon.DOT, name, MUTED, tag_edge(self.app.tag_color(name))))
        return parts

    def _draw_meta(self, task, parts, x, y, limit, tile, tag):
        canvas, scale = self.canvas, self.scale
        gap = round(12 * scale)
        for glyph, label, color, glyph_color in parts:
            if glyph:
                font = "dot" if glyph == Icon.DOT else "glyph"
                canvas.create_text(x, y, text=glyph, anchor="w", font=self.fonts.get(font), fill=resolve(glyph_color), tags=tag)
                x += self.fonts.measure(font, glyph) + round(4 * scale)
            if label:
                label = self.fonts.fit("meta", label, limit - x)
                canvas.create_text(x, y, text=label, anchor="w", font=self.fonts.get("meta"), fill=resolve(color), tags=tag)
                x += self.fonts.measure("meta", label)
            x += gap
            if x >= limit:
                return
        total = task["cp_total"]
        if total and x + round(70 * scale) < limit:
            bar, thickness = round(44 * scale), max(round(4 * scale), 2)
            top = y - thickness // 2
            rounded(canvas, x, top, x + bar, top + thickness, thickness / 2, resolve(TRACK), tile, tags=tag)
            filled = round(bar * task["cp_done"] / total)
            if filled:
                rounded(canvas, x, top, x + filled, top + thickness, thickness / 2, resolve(GREEN if filled == bar else ACCENT), resolve(TRACK), tags=tag)
            canvas.create_text(x + bar + round(6 * scale), y, text=f"{task['cp_done']}/{total}", anchor="w",
                               font=self.fonts.get("meta"), fill=resolve(MUTED), tags=tag)

    # ---------- Cuộn và tương tác ----------

    def _show_offset(self, position):
        """Đặt vị trí cuộn, gọi ở từng khung hình: dời các dòng đã vẽ, chỉ vẽ dòng mới lọt vào và xoá dòng vừa ra khỏi khung."""
        offset = round(max(min(position, self.total - self.canvas.winfo_height()), 0))
        if offset == self.offset or self.draw_pending:
            self.offset = offset  # sắp vẽ lại cả danh sách thì không cần dời gì
            return
        canvas = self.canvas
        canvas.move("rows", 0, self.offset - offset)
        self.offset = offset
        old, new = self.live, self._visible()
        if new.start >= old.stop or new.stop <= old.start:
            canvas.delete("rows")
            fresh = new
        else:
            for index in (*range(old.start, new.start), *range(new.stop, old.stop)):
                canvas.delete(f"row{index}")
            fresh = (*range(new.start, old.start), *range(old.stop, new.stop))
        self.live = new
        if fresh:
            width, now = self._row_width(), datetime.now()
            for index in fresh:
                self._draw_row(index, width, now)
        self.thumb.update(*self._view())
        if self.hover_index is not None:
            self._set_hover(None, False)  # dòng dưới con trỏ đã trôi đi, tô lại khi dừng

    def _on_settle(self):
        """Dừng cuộn thì tô lại dòng đang nằm dưới con trỏ."""
        canvas = self.canvas
        x, y = canvas.winfo_pointerx() - canvas.winfo_rootx(), canvas.winfo_pointery() - canvas.winfo_rooty()
        if 0 <= x < canvas.winfo_width() and 0 <= y < canvas.winfo_height() and not self.thumb.hit(x):
            index = self._index_at(y)
            is_task = index is not None and self.entries[index][0] == "task"
            self._set_hover(index if is_task else None, is_task and x < self.CHECK_WIDTH * self.scale)

    def _scroll_to(self, offset):
        """Nhảy thẳng tới vị trí, không trượt."""
        self.scroller.jump_to(offset)

    def _scroll_by(self, amount):
        self._scroll_to(self.offset + amount)

    def _index_at(self, y):
        if not self.entries:
            return None
        position = y + self.offset
        index = bisect_right(self.tops, position) - 1
        return index if 0 <= index and position < self.total else None

    def _set_hover(self, index, on_check):
        if index != self.hover_index or on_check != self.hover_check:
            previous, self.hover_index = self.hover_index, index
            self.hover_check = on_check
            self._schedule_rows(previous, index)

    def _on_motion(self, event):
        if self.thumb.hit(event.x):
            self._set_hover(None, False)
            return
        index = self._index_at(event.y)
        is_task = index is not None and self.entries[index][0] == "task"
        self._set_hover(index if is_task else None, is_task and event.x < self.CHECK_WIDTH * self.scale)

    def _on_click(self, event):
        self.canvas.focus_set()
        if self.thumb.hit(event.x):
            return
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
        if self.on_open and not self.thumb.hit(event.x) and index is not None and self.entries[index][0] == "task" and event.x >= self.CHECK_WIDTH * self.scale:
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
        """Dòng được chọn bằng bàn phím nằm ngoài khung thì trượt tới vừa đủ thấy."""
        index = self.index_of.get(task_id)
        if index is None:
            return
        top, bottom = self.tops[index], self.tops[index] + round(self.TILE * self.scale)
        height = self.canvas.winfo_height()
        target = self.scroller.glide.target if self.scroller.running else self.offset
        if top < target:
            self.scroller.glide_to(top)
        elif bottom > target + height:
            self.scroller.glide_to(bottom - height)

    def _toggle_selected(self):
        for entry in self.entries:
            if entry[0] == "task" and entry[1]["id"] == self.selected_id:
                self.on_toggle(entry[1])
                break
        return "break"


def draw_week(canvas, x0, y0, width, height, week, back, scale, tags):
    """Bảy cột nhỏ cạnh con số, cột cuối là hôm nay. back là màu nền ngay sau cột, đổi theo lúc rê chuột."""
    if not week or width < 20:
        return
    peak = max(max(count for _, count in week), 1)
    slot = width / 7
    bar = slot * 0.62
    for index, (_day, count) in enumerate(week):
        x = x0 + slot * index + slot / 2
        is_today = index == len(week) - 1
        size = max(round(height * count / peak), round(2 * scale))
        rounded(canvas, x - bar / 2, y0 + height - size, x + bar / 2, y0 + height, round(2 * scale),
                resolve((ACCENT if is_today else CHART_BAR) if count else TRACK), resolve(back), tags=tags)


class DayBand(tk.Canvas):
    """Dải 24 giờ của hôm nay chia theo 12 giờ âm lịch: ô xanh là giờ hoàng đạo, thanh dưới là khối giờ, vạch đỏ là bây giờ."""
    HEIGHT, LABEL, BAR = 58, 36, 16
    DAY_START = 23 * 60  # ngày theo giờ can chi bắt đầu từ giờ Tý, tức 23:00
    MINUTES = 1440
    FONTS = {"name": ("FONT_SEMIBOLD", 12, 0), "time": ("FONT_TEXT", 11, 0), "bar": ("FONT_TEXT", 11, 0)}

    def __init__(self, master, app):
        super().__init__(master, highlightthickness=0, bd=0, bg=resolve(CARD))
        self.app = app
        self.fonts = FontCache(self.FONTS)
        self.now = None
        self.slots = []
        self.bars = []
        self.marks = []
        self.bind("<Configure>", lambda _: self._paint())
        AppearanceModeTracker.add(lambda _mode: self._on_theme(), self)
        ScalingTracker.add_widget(self._on_scaling, self)
        self._on_scaling(ScalingTracker.get_widget_scaling(self))

    def _on_scaling(self, scale, _window=None):
        self.configure(height=round(self.HEIGHT * scale))

    def _on_theme(self):
        self.configure(bg=resolve(CARD))
        self._paint()

    def show(self, now, tasks, blocks):
        self.now = now
        self.slots = hours_of(now.date())
        self.bars = [(row, *block_window(row)) for row in blocks]
        self.marks = [task for task in tasks if task["due_at"] and not task["all_day"] and from_text(task["due_at"]).date() == now.date()]
        self._paint()

    def _x(self, moment, width):
        return ((moment.hour * 60 + moment.minute - self.DAY_START) % self.MINUTES) / self.MINUTES * width

    def _paint(self):
        self.delete("all")
        width = self.winfo_width()
        if not self.slots or width < 40:
            return
        scale = ScalingTracker.get_widget_scaling(self)
        self.fonts.rescale(scale)
        cell = width / 12
        label = round(self.LABEL * scale)
        for index, slot in enumerate(self.slots):
            x = index * cell
            rounded(self, x + 1, 0, x + cell - 1, label, round(theme.RADIUS_CONTROL * scale), resolve(GREEN_SOFT if slot.good else FIELD), resolve(CARD))
            color = GREEN if slot.good else MUTED
            self.create_text(x + cell / 2, label * 0.32, text=slot.name, font=self.fonts.get("name"), fill=resolve(color))
            self.create_text(x + cell / 2, label * 0.72, text=f"{slot.start}–{slot.end}", font=self.fonts.get("time"), fill=resolve(color))
        top = label + round(4 * scale)
        bottom = top + round(self.BAR * scale)
        self.create_line(0, (top + bottom) / 2, width, (top + bottom) / 2, fill=resolve(BORDER))
        for row, start, end in self.bars:
            x0, x1 = self._x(start, width), self._x(end, width)
            if x1 <= x0:
                x1 = width
            item = rounded(self, x0, top, x1, bottom, round(theme.RADIUS_CHIP * scale), resolve(FILL), resolve(CARD))
            title = self.fonts.fit("bar", row["title"], x1 - x0 - round(8 * scale))
            text = self.create_text(x0 + round(4 * scale), (top + bottom) / 2, text=title, anchor="w", font=self.fonts.get("bar"), fill=resolve(ON_FILL))
            for element in (item, text):
                self.tag_bind(element, "<Button-1>", lambda _event, task_id=row["id"]: self.app.open_task(task_id))
        for task in self.marks:
            x = self._x(from_text(task["due_at"]), width)
            size = round(5 * scale)
            item = self.create_polygon(x, top, x + size, (top + bottom) / 2, x, bottom, x - size, (top + bottom) / 2, outline="", fill=resolve(AMBER))
            self.tag_bind(item, "<Button-1>", lambda _event, task_id=task["id"]: self.app.open_task(task_id))
        x = self._x(self.now, width)
        self.create_line(x, 0, x, bottom, fill=resolve(RED), width=max(round(2 * scale), 1))


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
        set_window_rounded(self.winfo_id(), resolve(BORDER))
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
        fill, color = (FILL, ON_FILL) if day == self.current else (ACCENT_SOFT, ACCENT) if day == self.today else (None, TEXT)
        if fill:
            rounded(canvas, x + inset, y + inset, x + cell - inset, y + cell - inset, round(theme.RADIUS_CONTROL * self.scale), resolve(fill), resolve(CARD))
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
        super().__init__(master, fg_color=FILL, corner_radius=theme.RADIUS_CARD, height=44)
        self.label = Label(self, text="", font=theme.text(13), text_color=ON_FILL)
        self.label.pack(side="left", padx=(16, 10), pady=6)
        self.button = ctk.CTkButton(self, text="", width=70, height=28, corner_radius=theme.RADIUS_CHIP, fg_color="transparent",
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
