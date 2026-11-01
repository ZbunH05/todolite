"""Màu sắc, font và icon dùng chung. Mỗi màu là cặp (sáng, tối).

Theme tối là đen và xanh dương, tham khảo GitHub Dark High Contrast và Tokyo Night: nền gần
như đen, chỉ một màu xanh để nhấn, nên phần quan trọng nổi bật mà app vẫn tối giản. Mọi cặp
chữ/nền đều đạt tối thiểu 4,5:1 theo WCAG AA; chữ chính đạt trên 14:1.
"""
import tkinter.font as tkfont

import customtkinter as ctk

BG = ("#F2F6FC", "#05080F")
SIDEBAR = ("#E6EDF8", "#02040A")
CARD = ("#FFFFFF", "#0C1322")
CARD_HOVER = ("#EAF0FA", "#16213A")
FIELD = ("#F2F6FC", "#070C17")
BORDER = ("#D2DCEC", "#253552")
TEXT = ("#0A1324", "#F4F7FF")
MUTED = ("#46556E", "#A9BAD6")
ACCENT = ("#1456CC", "#6CB6FF")  # chữ, icon và thanh tiến độ nhấn trên nền tối
FILL = ("#1F5FE0", "#1F6FEB")  # nền nút chính, đi với chữ trắng
FILL_HOVER = ("#1A52C4", "#1A60D0")
ON_FILL = ("#FFFFFF", "#FFFFFF")
ACCENT_SOFT = ("#DCE8FF", "#14305C")
SEGMENT_SELECTED = ("#C4D8FF", "#1F6FEB")
RED = ("#BF2436", "#FF8A94")
RED_SOFT = ("#FBE2E5", "#3A1A24")
AMBER = ("#865500", "#F7C948")
AMBER_SOFT = ("#FBEFD3", "#3A2F12")
GREEN = ("#0B7342", "#45E08A")
GREEN_SOFT = ("#D5F3E3", "#10362A")
TRACK = ("#D9E2F0", "#1E2C47")
CHART_BAR = ("#A9C3F7", "#2B4F8C")

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


FONT_TEXT = "Segoe UI"
FONT_SEMIBOLD = "Segoe UI Semibold"
FONT_DISPLAY = "Segoe UI Semibold"
FONT_ICON = "Segoe Fluent Icons"


def init_fonts():
    """Chọn font Windows 11, lùi về Segoe UI nếu máy không có. Gọi sau khi đã có cửa sổ Tk."""
    global FONT_TEXT, FONT_SEMIBOLD, FONT_DISPLAY, FONT_ICON
    families = set(tkfont.families())
    if "Segoe UI Variable Text" in families:
        FONT_TEXT = "Segoe UI Variable Text"
        FONT_SEMIBOLD = "Segoe UI Variable Text Semibold"
    if "Segoe UI Variable Display Semib" in families:
        FONT_DISPLAY = "Segoe UI Variable Display Semib"
    if FONT_ICON not in families:
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
