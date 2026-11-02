"""Thanh bên vẽ trên một Canvas duy nhất, thay cho hàng trăm cửa sổ Tk mà mỗi mục CustomTkinter kéo theo.

Canvas không cắt được hình theo vùng, nên phần tag cuộn theo từng dòng nguyên: không có dòng nào lộ một nửa.
"""
import tkinter as tk

from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import AppearanceModeTracker
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from .. import APP_NAME
from ..easing import WHEEL_DELTA, Steps
from . import motion, theme
from .shapes import rounded
from .theme import FILL, Icon, ON_FILL, RAIL, RAIL_HOVER, RAIL_MUTED, RAIL_TEXT, resolve
from .widgets import FontCache

NAV_ITEMS = (("dashboard", Icon.HOME, "Tổng quan"), ("calendar", Icon.CALENDAR, "Lịch"), ("almanac", Icon.MOON, "Vạn niên"),
             ("pomodoro", Icon.TIMER, "Pomodoro"), ("today", Icon.TODAY, "Hôm nay"), ("upcoming", Icon.UPCOMING, "Sắp tới"),
             ("all", Icon.LIST, "Tất cả"), ("done", Icon.DONE, "Đã xong"))
SETTINGS_KEY = "settings"
PILL_SECONDS = 0.16


def _count_text(value):
    return value if isinstance(value, str) else str(value) if value else ""


class Item:
    """Một mục trên thanh bên. top là None khi mục đang nằm ngoài vùng nhìn thấy."""
    __slots__ = ("key", "glyph", "label", "count", "color", "top", "height")

    def __init__(self, key, glyph, label, color=None):
        self.key, self.glyph, self.label, self.color = key, glyph, label, color
        self.count = 0
        self.top = self.height = None


class Sidebar(tk.Canvas):
    WIDTH, INSET = 216, 10
    BRAND_TOP, LOGO, BRAND_BOTTOM = 16, 30, 14
    ROW, ROW_GAP, TAG_ROW = 38, 2, 32
    TAG_HEAD_TOP, TAG_HEAD, TAG_HEAD_BOTTOM, BOTTOM = 14, 20, 2, 12
    GLYPH_X, TEXT_X = 31, 50
    FONTS = {"brand": ("FONT_DISPLAY", 16, 0), "label": ("FONT_TEXT", 14, 0), "count": ("FONT_TEXT", 12, 0), "head": ("FONT_TEXT", 12, 0),
             "glyph": ("FONT_ICON", 16, 0), "dot": ("FONT_ICON", 10, 0), "logo": ("FONT_ICON", 15, 0)}

    def __init__(self, master, on_pick):
        super().__init__(master, highlightthickness=0, bd=0, bg=resolve(RAIL))
        self.on_pick = on_pick
        self.nav = [Item(key, glyph, label) for key, glyph, label in NAV_ITEMS]
        self.settings = Item(SETTINGS_KEY, Icon.SETTINGS, "Cài đặt")
        self.tags = []
        self.items = {item.key: item for item in (*self.nav, self.settings)}
        self.tag_signature = None
        self.active = None
        self.hover = None
        self.first_tag = 0  # dòng tag đầu tiên đang hiện
        self.tag_area = (0, 0)
        self.tag_slots = 0
        self.steps = Steps()
        self.pill_box = None  # (y, cao) của pill đang vẽ
        self.slide = motion.Slide(lambda box: self.place_pill(round(box[0]), round(box[1])), PILL_SECONDS)
        self.wheel_target = self
        self.scale = 1.0
        self.fonts = FontCache(self.FONTS)
        self.draw_pending = False
        self.bind("<Configure>", lambda _: self.schedule_draw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _: self._set_hover(None))
        self.bind("<Button-1>", self._on_click)
        AppearanceModeTracker.add(lambda _mode: self._on_theme(), self)
        ScalingTracker.add_widget(self._on_scaling, self)
        self._on_scaling(ScalingTracker.get_widget_scaling(self))

    def _size(self, value):
        return round(value * self.scale)

    def _on_scaling(self, scale, _window=None):
        self.scale = scale
        self.configure(width=round(self.WIDTH * scale))
        self.schedule_draw()

    def _on_theme(self):
        self.configure(bg=resolve(RAIL))
        self.schedule_draw()

    # ---------- Dữ liệu ----------

    def set_count(self, key, value):
        """Số đếm bên phải một mục, hoặc một chữ ngắn như đồng hồ Pomodoro đang chạy. Chỉ đổi đúng một hình trên Canvas."""
        item = self.items.get(key)
        if item is not None and value != item.count:
            item.count = value
            self.itemconfigure(f"count-{key}", text=_count_text(value))

    def set_tags(self, rows):
        """rows: các dòng tag từ Store. Đổi tên, đổi màu, thêm, xoá thì dựng lại danh sách, còn lại chỉ đổi số đếm."""
        signature = [(row["id"], row["name"], row["color"]) for row in rows]
        if signature != self.tag_signature:
            self.tag_signature = signature
            for item in self.tags:
                self.items.pop(item.key)
            self.tags = [Item(f"tag:{row['id']}", Icon.DOT, row["name"], (row["color"], row["color"])) for row in rows]
            self.items.update((item.key, item) for item in self.tags)
            self.schedule_draw()
        for row in rows:
            self.set_count(f"tag:{row['id']}", row["n"])

    # ---------- Bố cục ----------

    def _layout(self, height):
        """Tính vị trí mọi mục. Phần tag dùng hết chỗ giữa các mục chính và Cài đặt."""
        y = self._size(self.BRAND_TOP + self.LOGO + self.BRAND_BOTTOM)
        row, gap = self._size(self.ROW), self._size(self.ROW_GAP)
        for item in self.nav:
            item.top, item.height = y, row
            y += row + gap
        self.settings.top, self.settings.height = height - self._size(self.BOTTOM) - row, row
        self.tag_head_y = y + self._size(self.TAG_HEAD_TOP + self.TAG_HEAD / 2)
        top = y + self._size(self.TAG_HEAD_TOP + self.TAG_HEAD + self.TAG_HEAD_BOTTOM)
        bottom = self.settings.top - gap
        self.tag_area = (top, bottom)
        tag_row, step = self._size(self.TAG_ROW), self._size(self.TAG_ROW) + gap
        self.tag_slots = max((bottom - top + gap) // step, 0)
        self.first_tag = max(min(self.first_tag, len(self.tags) - self.tag_slots), 0)
        for index, item in enumerate(self.tags):
            slot = index - self.first_tag
            item.top = top + slot * step if 0 <= slot < self.tag_slots else None
            item.height = tag_row

    def visible_items(self):
        return [item for item in (*self.nav, *self.tags, self.settings) if item.top is not None]

    def _item_at(self, y):
        return next((item for item in self.visible_items() if item.top <= y < item.top + item.height), None)

    # ---------- Vẽ ----------

    def schedule_draw(self):
        if not self.draw_pending:
            self.draw_pending = True
            self.after_idle(self._paint)

    def _paint(self):
        self.draw_pending = False
        if not self.winfo_exists():
            return
        self.delete("all")
        self.pill_box = None
        self.scale = ScalingTracker.get_widget_scaling(self)
        self.fonts.rescale(self.scale)
        height = self.winfo_height()
        if height < 60:
            return
        self._layout(height)
        self._paint_brand()
        if self.tags and self.tag_slots:
            self.create_text(self._size(20), self.tag_head_y, text="Tag", anchor="w", font=self.fonts.get("head"), fill=resolve(RAIL_MUTED))
        for item in self.visible_items():
            self._paint_item(item)
        self._paint_tag_bar()
        self._paint_hover()
        self._sync_pill()

    def _paint_brand(self):
        x, y, size = self._size(16), self._size(self.BRAND_TOP), self._size(self.LOGO)
        rounded(self, x, y, x + size, y + size, self._size(theme.RADIUS_CONTROL), resolve(FILL), resolve(RAIL))
        self.create_text(x + size / 2, y + size / 2, text=Icon.CHECK, font=self.fonts.get("logo"), fill=resolve(ON_FILL))
        self.create_text(x + size + self._size(10), y + size / 2, text=APP_NAME, anchor="w", font=self.fonts.get("brand"), fill=resolve(RAIL_TEXT))

    def _paint_item(self, item):
        key, middle = item.key, item.top + item.height / 2
        active = key == self.active
        glyph_color = ON_FILL if active else item.color or RAIL_MUTED
        marks = (f"item-{key}",)
        self.create_text(self._size(self.GLYPH_X), middle, text=item.glyph, font=self.fonts.get("dot" if item.color else "glyph"), fill=resolve(glyph_color),
                         tags=(*marks, f"glyph-{key}"))
        text_x = self._size(self.TEXT_X)
        count_x = self.winfo_width() - self._size(self.INSET + 12)
        room = count_x - self._size(28) - text_x
        self.create_text(text_x, middle, text=self.fonts.fit("label", item.label, room), anchor="w", font=self.fonts.get("label"),
                         fill=resolve(ON_FILL if active else RAIL_TEXT), tags=(*marks, f"label-{key}"))
        self.create_text(count_x, middle, text=_count_text(item.count), anchor="e", font=self.fonts.get("count"),
                         fill=resolve(ON_FILL if active else RAIL_MUTED), tags=(*marks, f"count-{key}"))

    def _paint_tag_bar(self):
        """Dấu hiệu còn tag phía trên hoặc phía dưới: một thanh mảnh cạnh danh sách."""
        hidden = len(self.tags) - self.tag_slots
        if hidden <= 0 or not self.tag_slots:
            return
        top, bottom = self.tag_area
        span = bottom - top
        length = max(round(span * self.tag_slots / len(self.tags)), self._size(16))
        y = top + round((span - length) * self.first_tag / hidden)
        x = self.winfo_width() - self._size(5)
        rounded(self, x, y, x + self._size(3), y + length, self._size(2), resolve(RAIL_MUTED), resolve(RAIL))

    def _paint_hover(self):
        self.delete("hover")
        item = self.items.get(self.hover)
        if item is not None and item.top is not None and item.key != self.active:
            self._draw_pill_shape(item.top, item.height, RAIL_HOVER, "hover")
            self.tag_lower("hover")

    def _draw_pill_shape(self, y, height, fill, tag):
        x0, x1 = self._size(self.INSET), self.winfo_width() - self._size(self.INSET)
        rounded(self, x0, y, x1, y + height, self._size(theme.RADIUS_CONTROL), resolve(fill), resolve(RAIL), tags=(tag,))

    # ---------- Pill của mục đang chọn ----------

    def active_box(self):
        """(y, cao) của mục đang chọn, None nếu mục đó đang nằm ngoài vùng nhìn thấy."""
        item = self.items.get(self.active)
        return None if item is None or item.top is None else (item.top, item.height)

    def place_pill(self, y, height):
        """Đặt pill ở một vị trí bất kỳ. Cùng chiều cao thì chỉ dời các hình có sẵn, nên gọi được ở từng khung hình của animation."""
        if self.pill_box and self.pill_box[1] == height:
            self.move("pill", 0, y - self.pill_box[0])
        else:
            self.delete("pill")
            self._draw_pill_shape(y, height, FILL, "pill")
            self.tag_lower("pill")
            self.tag_lower("hover")
        self.pill_box = (y, height)

    def hide_pill(self):
        self.delete("pill")
        self.pill_box = None

    def _sync_pill(self):
        if self.slide.active:
            return  # đang trượt: khung kế tiếp tự vẽ lại pill
        box = self.active_box()
        if box:
            self.place_pill(*box)
        else:
            self.hide_pill()

    def set_active(self, key):
        """Chọn mục đang mở. Đây là nơi duy nhất làm pill đổi chỗ: pill trượt tới mục mới trong lúc nội dung mờ dần, chuyển động
        có chủ đích duy nhất của app."""
        if key == self.active:
            return
        previous, self.active = self.active, key
        start = self.pill_box
        self.slide.cancel()
        if self._reveal(key):
            return
        for changed in (previous, key):
            self._recolor(changed)
        self._set_hover(self.hover, force=True)
        end = self.active_box()
        if start and end:
            self.slide.run(start, end)
        else:
            self._sync_pill()

    def _recolor(self, key):
        item = self.items.get(key)
        if item is None:
            return
        active = key == self.active
        self.itemconfigure(f"glyph-{key}", fill=resolve(ON_FILL if active else item.color or RAIL_MUTED))
        self.itemconfigure(f"label-{key}", fill=resolve(ON_FILL if active else RAIL_TEXT))
        self.itemconfigure(f"count-{key}", fill=resolve(ON_FILL if active else RAIL_MUTED))

    def _reveal(self, key):
        """Tag đang chọn nằm ngoài vùng nhìn thấy thì cuộn tới. Trả về True nếu phải vẽ lại cả thanh."""
        item = self.items.get(key)
        if item is None or item not in self.tags or item.top is not None:
            return False
        self.first_tag = max(self.tags.index(item) - self.tag_slots + 1, 0)
        self.schedule_draw()
        return True

    # ---------- Tương tác ----------

    def _set_hover(self, key, force=False):
        if key != self.hover or force:
            self.hover = key
            self._paint_hover()
            self.configure(cursor="hand2" if key else "")

    def _on_motion(self, event):
        item = self._item_at(event.y)
        self._set_hover(item.key if item else None)

    def _on_click(self, event):
        item = self._item_at(event.y)
        if item:
            self.on_pick(item.key)

    def wheel(self, delta, _touchpad=False, event=None):
        """Cuộn tag theo dòng nguyên, mỗi nấc bằng số dòng trong cài đặt của Windows. Bàn di chuột cộng dồn cho đủ một dòng."""
        top, bottom = self.tag_area
        if event is None or not top <= event.y < bottom or len(self.tags) <= self.tag_slots:
            return
        steps = self.steps.feed(-delta / WHEEL_DELTA * motion.page_lines(self.tag_slots))
        if steps:
            first = max(min(self.first_tag + steps, len(self.tags) - self.tag_slots), 0)
            if first != self.first_tag:
                self.first_tag = first
                self.schedule_draw()
