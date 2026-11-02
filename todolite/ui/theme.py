"""Màu sắc, font và icon dùng chung. Mỗi màu là cặp (sáng, tối). Xem thêm DESIGN.md.

Cả hai theme chung một khung xanh đen: thanh bên và thanh tiêu đề giữ nguyên khi đổi theme, nên
app luôn nhận ra được. Bên trong là nền gần đen hoặc gần trắng, chỉ một màu xanh để nhấn. Mọi cặp
chữ/nền đều đạt tối thiểu 4,5:1 theo WCAG AA; chữ chính đạt trên 14:1.

Cỡ chữ theo vai trò, không dùng số nào khác: 12 ghi chú, 13 phụ và nút, 14 nội dung, 16 tiêu đề
khối, 24 tiêu đề trang, 32 số liệu, 48 đồng hồ, 72 ngày trên tờ lịch. Riêng ô lịch dày được dùng 11.
Tuỳ chọn cỡ chữ phóng to toàn bộ các số đó qua hệ số của CustomTkinter, nên bố cục giữ nguyên tỉ lệ.
"""
import os
import tkinter.font as tkfont

import customtkinter as ctk

from ..paths import FONT_PATHS
from ..win32 import load_private_fonts

BG = ("#EEF2F9", "#05080F")
RAIL = ("#0B1B3D", "#091228")  # khung xanh đen, chữ trên khung luôn sáng ở cả hai theme
RAIL_HOVER = ("#17294F", "#141F3B")
RAIL_TEXT = ("#EEF3FD", "#EEF3FD")
RAIL_MUTED = ("#AFBFDC", "#AFBFDC")
SUNKEN = ("#F4F7FC", "#080D18")  # ô ngoài tháng trên lịch
CARD = ("#FFFFFF", "#0C1322")
CARD_HOVER = ("#EAF0FA", "#16213A")
FIELD = ("#F2F6FC", "#070C17")
BORDER = ("#DCE4F0", "#1D2A44")
TEXT = ("#0A1324", "#F4F7FF")
MUTED = ("#46556E", "#A9BAD6")
ACCENT = ("#1456CC", "#6CB6FF")  # chữ, icon và thanh tiến độ nhấn trên nền tối
FILL = ("#1F5FE0", "#1F6FEB")  # nền nút chính, đi với chữ trắng
FILL_HOVER = ("#1A52C4", "#1A60D0")
ON_FILL = ("#FFFFFF", "#FFFFFF")
ACCENT_SOFT = ("#DCE8FF", "#14305C")
SEGMENT_SELECTED = ("#C4D8FF", "#1A60D0")
RED = ("#BF2436", "#FF8A94")
RED_SOFT = ("#FBE2E5", "#3A1A24")
RED_SOFT_HOVER = ("#F9DADE", "#522731")
RED_EDGE = ("#E08C96", "#A65862")
AMBER = ("#865500", "#F7C948")
AMBER_SOFT = ("#FBEFD3", "#3A2F12")
GREEN = ("#0B7342", "#45E08A")
GREEN_SOFT = ("#D5F3E3", "#10362A")
GREEN_SOFT_HOVER = ("#CBEDDB", "#164A36")
GREEN_EDGE = ("#7AB99B", "#2D945F")
TRACK = ("#D9E2F0", "#1E2C47")
SWITCH_OFF = ("#8D9DB8", "#3B4C6C")
SWITCH_KNOB = ("#0B1B3D", "#EEF3FD")  # núm công tắc nhô ra khỏi rãnh nên phải nổi trên nền thẻ
CHART_BAR = ("#A9C3F7", "#2B4F8C")

# Bán kính bo góc: thẻ và thẻ việc, phần tử nằm trong thẻ (nút, ô nhập, ô lịch), mảnh nhỏ (mục trên lịch, nhãn)
RADIUS_CARD, RADIUS_CONTROL, RADIUS_CHIP = 12, 8, 6

TAG_FALLBACK = "#4DA3FF"
PRIORITY_COLORS = {0: MUTED, 1: ACCENT, 2: AMBER, 3: RED}
PRIORITY_LABELS = ("Không", "Thấp", "Vừa", "Cao")


class Icon:
    """Mã ký tự của font Segoe Fluent Icons, có sẵn trên mọi máy Windows 11."""
    HOME = ""
    TODAY = ""
    CALENDAR = ""
    UPCOMING = ""
    LIST = ""
    DONE = ""
    SETTINGS = ""
    ADD = ""
    CLOSE = ""
    DELETE = ""
    REPEAT = ""
    TIMER = ""
    TAG = ""
    SEARCH = ""
    PLAY = ""
    STOP = ""
    CLOCK = ""
    LEFT = ""
    RIGHT = ""
    RING = ""
    DOT = ""
    CHECK = ""
    CHECKLIST = ""
    WARNING = ""
    CHART = ""
    MOON = "\ue708"
    REMOVE = "\ue738"


FONT_TEXT = "Segoe UI"
FONT_SEMIBOLD = "Segoe UI Semibold"
FONT_DISPLAY = "Segoe UI Semibold"
FONT_ICON = "Segoe Fluent Icons"
TEXT_SCALES = {"Vừa": "1", "Lớn": "1.15", "Rất lớn": "1.3"}


def init_fonts():
    """Dùng Be Vietnam Pro đi kèm app: nét rõ ở cỡ nhỏ, dấu tiếng Việt được vẽ riêng. Thiếu file thì lùi về font Windows."""
    global FONT_TEXT, FONT_SEMIBOLD, FONT_DISPLAY, FONT_ICON
    families = ()
    if load_private_fonts(FONT_PATHS):
        FONT_TEXT, FONT_SEMIBOLD, FONT_DISPLAY = "Be Vietnam Pro", "Be Vietnam Pro SemiBold", "Be Vietnam Pro SemiBold"
    else:
        families = set(tkfont.families())
        if "Segoe UI Variable Text" in families:
            FONT_TEXT = "Segoe UI Variable Text"
            FONT_SEMIBOLD = FONT_DISPLAY = "Segoe UI Variable Text Semibold"
    # Windows 11 luôn kèm SegoeIcons.ttf: xem file rẻ hơn liệt kê cả ~300 font đã cài
    if not os.path.exists(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "SegoeIcons.ttf")):
        if FONT_ICON not in (families or set(tkfont.families())):
            FONT_ICON = "Segoe MDL2 Assets"


def text(size):
    return (FONT_TEXT, size)


def semibold(size):
    return (FONT_SEMIBOLD, size)


def display(size):
    return (FONT_DISPLAY, size)


def icon(size):
    return (FONT_ICON, size)


def resolve(pair):
    """Màu thực tế theo theme hiện tại, dùng cho Canvas tự vẽ."""
    return pair[1] if ctk.get_appearance_mode() == "Dark" else pair[0]


def blend(front, back, alpha):
    """Pha hai màu '#RRGGBB'. Canvas Tk không có độ trong suốt nên phải tính trước."""
    channels = (round(int(front[i:i + 2], 16) * alpha + int(back[i:i + 2], 16) * (1 - alpha)) for i in (1, 3, 5))
    return "#" + "".join(f"{channel:02X}" for channel in channels)


def tag_tint(color):
    """Nền nhạt của một tag: chữ trên nền này luôn đạt tương phản trên 9:1."""
    return blend(color, CARD[0], 0.18), blend(color, CARD[1], 0.24)


def tag_edge(color):
    """Màu nét của tag. Màu tag vốn hợp nền tối, nên trên nền sáng cần đậm hơn để còn thấy rõ."""
    return blend(color, "#000000", 0.68), color
