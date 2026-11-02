"""Chuyển động của giao diện: một vòng khung hình dùng chung, cuộn mượt cho mọi bề mặt, con trượt mảnh và chuyển cảnh mờ dần.

Vòng khung hình chỉ chạy khi có thứ đang chuyển động và tắt hẳn khi đứng yên, nên app rảnh không có thêm bộ hẹn giờ nào.
Tắt "Hiệu ứng hoạt hình" trong Windows thì cuộn nhảy thẳng tới đích và chuyển cảnh tức thì, không phủ gì lên cửa sổ.
"""
import ctypes
import sys
import tkinter as tk
from ctypes import Structure, byref, c_int, c_ubyte, c_void_p
from ctypes import wintypes as w
from time import perf_counter

import customtkinter as ctk
from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import AppearanceModeTracker
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from ..easing import (TOUCH_TAU, WHEEL_DELTA, WHEEL_PAGESCROLL, WHEEL_TAU, Glide, Swipe, ease_out, frame_period, mix, notch_pixels,
                      thumb_box, thumb_offset, touchpad_delta)
from .shapes import rounded
from .theme import MUTED, blend, resolve

SPI_GETWHEELSCROLLLINES, SPI_GETCLIENTAREAANIMATION = 0x0068, 0x1042
WS_POPUP = 0x80000000
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = 0x80000, 0x20, 0x8000000, 0x80
SRCCOPY, ULW_ALPHA, SW_SHOWNOACTIVATE, GA_ROOT, VREFRESH = 0x00CC0020, 2, 4, 2, 116
FADE_SECONDS = 0.16
STALL_STEP = 0.025  # một khung bị chặn lâu chỉ được tính chừng hai khung, để pill chậm lại một chút thay vì nhảy cóc tới đích
HOLD_FRAMES = 2  # số khung hình giữ nguyên ảnh cũ để Tk vẽ xong trang mới


class BLENDFUNCTION(Structure):
    _fields_ = [("op", c_ubyte), ("flags", c_ubyte), ("alpha", c_ubyte), ("format", c_ubyte)]


class SIZE(Structure):
    _fields_ = [("cx", w.LONG), ("cy", w.LONG)]


def _bind(dll, name, restype, *argtypes):
    function = getattr(dll, name)
    function.restype, function.argtypes = restype, argtypes
    return function


_user32, _gdi32, _winmm = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32"), ctypes.WinDLL("winmm")
SystemParametersInfoW = _bind(_user32, "SystemParametersInfoW", w.BOOL, w.UINT, w.UINT, c_void_p, w.UINT)
GetDC = _bind(_user32, "GetDC", w.HDC, w.HWND)
ReleaseDC = _bind(_user32, "ReleaseDC", c_int, w.HWND, w.HDC)
GetAncestor = _bind(_user32, "GetAncestor", w.HWND, w.HWND, w.UINT)
CreateWindowExW = _bind(_user32, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, c_int, c_int, c_int, c_int,
                        w.HWND, w.HMENU, w.HINSTANCE, c_void_p)
UpdateLayeredWindow = _bind(_user32, "UpdateLayeredWindow", w.BOOL, w.HWND, w.HDC, c_void_p, c_void_p, w.HDC, c_void_p, w.COLORREF,
                            c_void_p, w.DWORD)
ShowWindow = _bind(_user32, "ShowWindow", w.BOOL, w.HWND, c_int)
DestroyWindow = _bind(_user32, "DestroyWindow", w.BOOL, w.HWND)
IsIconic = _bind(_user32, "IsIconic", w.BOOL, w.HWND)
IsWindowVisible = _bind(_user32, "IsWindowVisible", w.BOOL, w.HWND)
GetWindowRect = _bind(_user32, "GetWindowRect", w.BOOL, w.HWND, ctypes.POINTER(w.RECT))
CreateCompatibleDC = _bind(_gdi32, "CreateCompatibleDC", w.HDC, w.HDC)
CreateCompatibleBitmap = _bind(_gdi32, "CreateCompatibleBitmap", w.HBITMAP, w.HDC, c_int, c_int)
SelectObject = _bind(_gdi32, "SelectObject", w.HGDIOBJ, w.HDC, w.HGDIOBJ)
DeleteObject = _bind(_gdi32, "DeleteObject", w.BOOL, w.HGDIOBJ)
DeleteDC = _bind(_gdi32, "DeleteDC", w.BOOL, w.HDC)
BitBlt = _bind(_gdi32, "BitBlt", w.BOOL, w.HDC, c_int, c_int, c_int, c_int, w.HDC, c_int, c_int, w.DWORD)
GdiAlphaBlend = _bind(_gdi32, "GdiAlphaBlend", w.BOOL, w.HDC, c_int, c_int, c_int, c_int, w.HDC, c_int, c_int, c_int, c_int, BLENDFUNCTION)
GetDeviceCaps = _bind(_gdi32, "GetDeviceCaps", c_int, w.HDC, c_int)
timeBeginPeriod = _bind(_winmm, "timeBeginPeriod", w.UINT, w.UINT)
timeEndPeriod = _bind(_winmm, "timeEndPeriod", w.UINT, w.UINT)

_driver = None


def system_animation():
    """Cài đặt Hiệu ứng hoạt hình của Windows. Hỏi mỗi lần cần vì chỉ tốn vài micro giây và người dùng đổi được bất cứ lúc nào."""
    value = w.BOOL(1)
    SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, byref(value), 0)
    return bool(value.value)


def wheel_lines():
    value = w.UINT(3)
    SystemParametersInfoW(SPI_GETWHEELSCROLLLINES, 0, byref(value), 0)
    return value.value


def _refresh_rate():
    screen = GetDC(None)
    try:
        return GetDeviceCaps(screen, VREFRESH)
    finally:
        ReleaseDC(None, screen)


# ---------- Vòng khung hình ----------

class Animator:
    """Một vòng after() duy nhất cho mọi chuyển động. Mỗi việc là hàm f(now, dt) trả về True nếu còn chạy tiếp.

    Bộ hẹn giờ của Windows mặc định 15,6 ms nên after(16) có lúc rơi vào 31 ms: chỉ trong lúc có chuyển động mới xin độ phân giải 1 ms.
    """

    def __init__(self, root):
        self.root = root
        self.tasks = []
        self.job = None
        self.period = frame_period(_refresh_rate())
        self.last = self.due = 0.0
        self.ticking = False

    @property
    def running(self):
        return self.job is not None

    def add(self, task):
        if task not in self.tasks:
            self.tasks.append(task)
        if self.job is None and not self.ticking:  # đang trong một khung thì khung đó tự hẹn khung kế, không mở vòng thứ hai
            timeBeginPeriod(1)
            self.last = self.due = perf_counter()
            self._schedule()

    def discard(self, task):
        if task in self.tasks:
            self.tasks.remove(task)  # vòng tự tắt ở khung kế tiếp nếu không còn việc

    def _schedule(self):
        now = perf_counter()
        self.due = max(self.due + self.period, now + 0.001)  # khung trễ thì bắt nhịp lại, không dồn khung bù
        self.job = self.root.after(max(round((self.due - now) * 1000), 1), self._tick)

    def _tick(self):
        self.job = None
        now = perf_counter()
        dt, self.last = now - self.last, now
        self.ticking = True
        try:
            for task in tuple(self.tasks):
                try:
                    keep = task(now, dt)
                except Exception:
                    keep = False
                    self.root.report_callback_exception(*sys.exc_info())
                if not keep and task in self.tasks:
                    self.tasks.remove(task)
        finally:
            self.ticking = False
        if self.tasks:
            self._schedule()
        else:
            timeEndPeriod(1)

    def stop(self):
        self.tasks.clear()
        if self.job is not None:
            self.root.after_cancel(self.job)
            self.job = None
            timeEndPeriod(1)


def install(root):
    """Tạo vòng khung hình và định tuyến con lăn cho cả cửa sổ. Gọi một lần khi dựng App."""
    global _driver
    _driver = Animator(root)
    root.bind_all("<MouseWheel>", lambda event: _route(event, event.delta))
    try:
        root.bind_all("<TouchpadScroll>", _on_touchpad)
    except tk.TclError:
        pass  # Tk 8.6 không có sự kiện này, nấc nhỏ của bàn di chuột đã được gom thành <MouseWheel>
    return _driver


def driver():
    return _driver


# ---------- Định tuyến con lăn ----------

def _on_touchpad(event):
    return _route(event, *touchpad_delta(event.delta))


def _route(event, delta, touchpad=False):
    """Đưa con lăn tới bề mặt cuộn nằm dưới con trỏ, kể cả khi con trỏ đang ở một widget con của bề mặt đó.

    Tk 9 chỉ biến nấc tròn 120 thành <MouseWheel>, còn bàn di chuột gửi nấc lẻ thành <TouchpadScroll> mà trước đây không ai nhận.
    """
    widget = event.widget
    while delta and isinstance(widget, tk.Misc):
        target = widget.__dict__.get("wheel_target")
        if target is not None:
            target.wheel(delta, touchpad, event)
            return "break"
        if isinstance(widget, tk.Text) and widget.yview() != (0.0, 1.0):
            return None  # ô ghi chú nhiều dòng tự cuộn bằng ràng buộc sẵn có của Tk
        widget = widget.master
    return None


def capture(widget, target):
    """Widget có ràng buộc con lăn riêng ở mức lớp (như Text) thì chặn ngay ở widget, không để nó cuộn nhảy trước."""
    widget.wheel_target = target
    widget.bind("<MouseWheel>", lambda event: _route(event, event.delta))
    try:
        widget.bind("<TouchpadScroll>", _on_touchpad)
    except tk.TclError:
        pass


# ---------- Cuộn mượt ----------

class Scroller:
    """Cuộn mượt cho một bề mặt bất kỳ, qua ba hàm: read() vị trí hiện tại, write(px) đặt vị trí, extent() trả về (cao nội dung, cao khung).

    Con lăn dời đích theo cài đặt số dòng mỗi nấc của Windows, mỗi khung hình đi một phần quãng còn lại nên dừng êm, nấc dồn dập thì cộng dồn.
    Bàn di chuột đi theo tỉ lệ và gần như bám sát ngón tay, vì Windows đã tự gửi quán tính.
    """

    def __init__(self, widget, read, write, extent, on_settle=None):
        self.widget = widget
        self.read, self.write, self.extent = read, write, extent
        self.on_settle = on_settle
        self.glide = Glide()
        self.running = False
        widget.wheel_target = self

    def _prepare(self):
        total, viewport = self.extent()
        limit = max(total - viewport, 0)
        if self.running:
            self.glide.limit = limit
            self.glide.aim(self.glide.target, self.glide.tau)
        else:
            self.glide.reset(self.read(), limit)  # vị trí có thể đã đổi ngoài luồng này, như khi kéo con trượt
        return viewport

    def wheel(self, delta, touchpad=False, _event=None):
        viewport = self._prepare()
        if not self.glide.limit:
            return
        lines = wheel_lines()
        if not lines:
            return
        pixels = notch_pixels(lines, viewport, ScalingTracker.get_widget_scaling(self.widget)) * delta / WHEEL_DELTA
        self.glide.push(-pixels, TOUCH_TAU if touchpad else WHEEL_TAU)
        self._run()

    def glide_to(self, position):
        self._prepare()
        self.glide.aim(position)
        self._run()

    def jump_to(self, position):
        self._prepare()
        self.glide.aim(position)
        self.stop()

    def halt(self):
        """Dừng tại chỗ, không ghi gì: bề mặt vừa tự đặt lại vị trí."""
        if self.running:
            self.running = False
            _driver.discard(self._frame)

    def stop(self):
        """Đặt ngay vào đích và dừng."""
        self.glide.finish()
        self.write(self.glide.position)
        if self.running:
            self.running = False
            _driver.discard(self._frame)
        if self.on_settle:
            self.on_settle()

    def _run(self):
        if self.glide.position == self.glide.target:
            return
        if not system_animation() or _driver is None:
            self.stop()
        elif not self.running:
            self.running = True
            _driver.add(self._frame)

    def _frame(self, _now, dt):
        if not self.running or not self.widget.winfo_exists():
            self.running = False
            return False
        moving = self.glide.step(dt)
        self.write(self.glide.position)
        if not moving:
            self.running = False
            if self.on_settle:
                self.on_settle()
        return moving


def canvas_scroller(canvas, on_settle=None):
    """Scroller cho Canvas cuộn bằng scrollregion, như tờ lịch và khung cuộn của CustomTkinter.

    Dời theo từng điểm ảnh bằng yview scroll thay vì moveto: moveto đi qua tỉ lệ nên làm tròn lệch một điểm ảnh ở cuối.
    """
    canvas.configure(yscrollincrement=1)
    top = [0.0]  # đỉnh scrollregion, đọc lại mỗi lần có nấc mới thay vì mỗi khung hình

    def extent():
        region = canvas.cget("scrollregion").split()
        if len(region) != 4:
            return 0.0, canvas.winfo_height()
        top[0] = float(region[1])
        return float(region[3]) - top[0] + 1, canvas.winfo_height()  # Tk tính cả hàng điểm ảnh ở cạnh dưới

    def read():
        return canvas.canvasy(0) - top[0]

    def write(position):
        step = round(position) - round(read())
        if step:
            canvas.yview_scroll(step, "units")

    return Scroller(canvas, read, write, extent, on_settle)


def text_scroller(text):
    """Scroller cho tk.Text: đo chiều cao theo điểm ảnh đã dàn trang, đặt vị trí bằng tỉ lệ."""
    total = [1.0]

    def extent():
        text.tk.call(text._w, "sync")  # Text đo chiều cao dòng dần dần khi rảnh, đo cho xong trước khi lấy tổng
        total[0] = float(text.tk.call(text._w, "count", "-ypixels", "1.0", "end")) or 1.0
        return total[0], text.winfo_height()

    scroller = Scroller(text, lambda: text.yview()[0] * total[0], lambda position: text.yview_moveto(position / total[0]), extent)
    capture(text, scroller)
    return scroller


class Stepper:
    """Con lăn lật từng bước, như lật tháng. Nấc con lăn thật lật ngay, bàn di chuột phải gom đủ một nấc và mỗi lần vuốt chỉ lật một bước."""

    def __init__(self, widget, on_step):
        self.on_step = on_step
        self.swipe = Swipe()
        widget.wheel_target = self

    def wheel(self, delta, touchpad=False, _event=None):
        step = self.swipe.feed(delta, perf_counter()) if touchpad else (-1 if delta > 0 else 1)
        if step:
            self.on_step(step)


def page_lines(viewport_lines):
    """Số dòng một nấc cho những chỗ cuộn theo dòng nguyên: cài đặt cuộn theo trang thì một nấc là một trang."""
    lines = wheel_lines()
    return viewport_lines if lines == WHEEL_PAGESCROLL else lines


# ---------- Con trượt ----------

class Thumb:
    """Con trượt mảnh kiểu Windows 11 vẽ ngay trên Canvas: mảnh khi đang cuộn, to ra khi rê chuột tới, kéo được, bấm vào rãnh
    thì trượt tới chỗ bấm, đứng yên một lúc hoặc nội dung vừa khung thì ẩn. Mỗi khung hình chỉ dời vài hình, không dàn lại bố cục
    như CTkScrollbar.set()."""
    THIN, WIDE, EDGE, MIN_LENGTH, IDLE = 3, 6, 3, 32, 1.0

    def __init__(self, canvas, scroller, back):
        self.canvas, self.scroller, self.back = canvas, scroller, back
        self.view = (0.0, 1.0)
        self.box = None  # (x0, y0, x1, y1) đang vẽ
        self.wide = False
        self.drag = None  # khoảng cách từ đỉnh con trượt tới chỗ bấm
        self.until = 0.0
        self.job = None
        canvas.bind("<Motion>", self._on_motion, add="+")
        canvas.bind("<Leave>", lambda _: self._set_wide(False), add="+")
        canvas.bind("<ButtonPress-1>", self._on_press, add="+")
        canvas.bind("<B1-Motion>", self._on_drag, add="+")
        canvas.bind("<ButtonRelease-1>", self._on_release, add="+")

    def _scaled(self, value):
        return round(value * ScalingTracker.get_widget_scaling(self.canvas))

    def zone_width(self):
        return self._scaled(self.WIDE + 2 * self.EDGE)

    def scrollable(self):
        return self.view[1] - self.view[0] < 1

    def hit(self, x):
        """True nếu x nằm trong rãnh của con trượt, để bề mặt bỏ qua cú bấm đó."""
        return self.scrollable() and x >= self.canvas.winfo_width() - self.zone_width()

    def _geometry(self):
        height = self.canvas.winfo_height()
        edge = self._scaled(self.EDGE)
        track = height - 2 * edge
        box = thumb_box(self.view[0], 1.0, self.view[1] - self.view[0], track, self._scaled(self.MIN_LENGTH))
        if box is None:
            return None
        size = self._scaled(self.WIDE if self.wide or self.drag is not None else self.THIN)
        x1 = self.canvas.winfo_width() - edge
        y0 = edge + round(box[0])
        return x1 - size, y0, x1, y0 + round(box[1])

    def update(self, first, last, wake=True):
        """Báo vị trí mới. wake=False khi chỉ vẽ lại (đổi cỡ, dữ liệu mới): con trượt đang ẩn thì vẫn ẩn."""
        moved = (first, last) != self.view
        self.view = (first, last)
        if not self.scrollable():
            self.hide()
        elif self.box is not None or (wake and moved):
            self._draw()
            self._arm()

    def wake(self):
        if self.box is None and self.scrollable():
            self._draw()
        if self.box is not None:
            self._arm()

    def refresh(self):
        """Canvas vừa xoá sạch hoặc đổi theme: vẽ lại nếu đang hiện."""
        if self.box is not None:
            self.box = None
            self.canvas.delete("thumb")
            self._draw()

    def hide(self):
        if self.box is not None:
            self.canvas.delete("thumb")
            self.box = None

    def forget(self):
        """Canvas đã tự xoá hết hình, chỉ cần quên con trượt cũ."""
        self.box = None

    def _draw(self):
        box = self._geometry()
        if box is None:
            self.hide()
            return
        old = self.box
        if old is not None and (old[0], old[2], old[3] - old[1]) == (box[0], box[2], box[3] - box[1]):
            if box[1] != old[1]:
                self.canvas.move("thumb", 0, box[1] - old[1])
        else:
            self.canvas.delete("thumb")
            back = resolve(self.back)
            color = resolve(MUTED) if self.wide or self.drag is not None else blend(resolve(MUTED), back, 0.6)
            rounded(self.canvas, *box, (box[2] - box[0]) / 2, color, back, tags=("thumb",))
        self.box = box

    def _arm(self):
        """Hẹn ẩn: một after duy nhất, cuộn liên tục chỉ dời mốc thời gian chứ không tạo lại bộ hẹn giờ."""
        self.until = perf_counter() + self.IDLE
        if self.job is None:
            self.job = self.canvas.after(round(self.IDLE * 1000), self._expire)

    def _expire(self):
        self.job = None
        if self.box is None:
            return
        left = self.until - perf_counter()
        if self.wide or self.drag is not None:
            self._arm()
        elif left > 0.01:
            self.job = self.canvas.after(round(left * 1000), self._expire)
        else:
            self.hide()

    def _set_wide(self, wide):
        if wide != self.wide and self.drag is None:
            self.wide = wide
            if self.box is not None or wide:
                self.box = None
                self.canvas.delete("thumb")
                self._draw()
                self._arm()

    def _on_motion(self, event):
        if self.drag is None:
            inside = self.hit(event.x)
            self._set_wide(inside)
            if not inside:
                self.wake()

    def _on_press(self, event):
        if not self.hit(event.x):
            return
        self.wide = True
        self._draw()
        box = self.box
        if box and box[1] <= event.y < box[3]:
            self.drag = event.y - box[1]
        else:
            total, viewport = self.scroller.extent()
            length = box[3] - box[1] if box else 0
            track = self.canvas.winfo_height() - 2 * self._scaled(self.EDGE)
            self.scroller.glide_to(thumb_offset(event.y - self._scaled(self.EDGE) - length / 2, total, viewport, track, length))

    def _on_drag(self, event):
        if self.drag is None or self.box is None:
            return
        total, viewport = self.scroller.extent()
        track = self.canvas.winfo_height() - 2 * self._scaled(self.EDGE)
        self.scroller.jump_to(thumb_offset(event.y - self._scaled(self.EDGE) - self.drag, total, viewport, track, self.box[3] - self.box[1]))

    def _on_release(self, event):
        if self.drag is not None:
            self.drag = None
            self.wide = self.hit(event.x) and 0 <= event.y < self.canvas.winfo_height()
            self.refresh()
            self._arm()


class ScrollStrip(tk.Canvas):
    """Rãnh hẹp cạnh một bề mặt cuộn bằng scrollregion hoặc Text, thay cho CTkScrollbar. Nối vào yscrollcommand của bề mặt."""

    def __init__(self, master, back):
        super().__init__(master, highlightthickness=0, bd=0, bg=resolve(back), width=1)
        self.back = back
        self.thumb = None
        AppearanceModeTracker.add(lambda _mode: self._on_theme(), self)
        ScalingTracker.add_widget(self._on_scaling, self)
        self._on_scaling(ScalingTracker.get_widget_scaling(self))

    def _on_scaling(self, scale, _window=None):
        self.configure(width=round((Thumb.WIDE + 2 * Thumb.EDGE) * scale))

    def _on_theme(self):
        self.configure(bg=resolve(self.back))
        if self.thumb:
            self.thumb.refresh()

    def attach(self, scroller, surface=None):
        """surface là widget nội dung: con trỏ đi vào đó thì con trượt hiện ra để báo còn nội dung."""
        self.thumb = Thumb(self, scroller, self.back)
        self.bind("<Configure>", lambda _: self.thumb.refresh())
        if surface is not None:
            surface.bind("<Enter>", lambda _: self.thumb.wake(), add="+")
        return self

    def set(self, first, last):
        if self.thumb:
            self.thumb.update(float(first), float(last))


class ScrollFrame(ctk.CTkScrollableFrame):
    """CTkScrollableFrame cuộn mượt với con trượt mảnh.

    Bản gốc gắn năm ràng buộc toàn cục cho mỗi khung (con lăn và phím Shift), không gỡ khi khung bị huỷ, và cuộn nhảy 20 điểm ảnh mỗi nấc.
    """

    def __init__(self, master, back, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._scrollbar.destroy()
        self._scrollbar = ScrollStrip(self._parent_frame, back)
        self._parent_canvas.configure(yscrollcommand=self._scrollbar.set)
        self._create_grid()
        self.scroller = canvas_scroller(self._parent_canvas)
        self.wheel_target = self.scroller
        self._scrollbar.attach(self.scroller, self._parent_canvas)

    def bind_all(self, sequence=None, func=None, add=None):
        return None


# ---------- Chuyển cảnh ----------

class CrossFade:
    """Chuyển cảnh mờ dần. Chụp vùng cần đổi vào bộ nhớ, phủ ảnh đó lên bằng một cửa sổ lớp trong suốt với chuột và không nhận
    focus, đổi giao diện bên dưới, đợi Tk vẽ xong rồi cho ảnh cũ mờ đi. Che luôn cảnh Tk vẽ dở từng mảnh khi trang hiện ra và
    những lần dựng trang lần đầu hơi lâu: ảnh cũ đứng yên cho tới khi trang mới sẵn sàng.

        with app.fade():          # cả vùng nội dung
        with app.fade(editor):    # chỉ một vùng
    """

    def __init__(self, root, region):
        self.root, self.default = root, region
        self.top = None
        self.depth = 0
        self.pending = None
        self.enabled = True
        self.region = None
        self.window = None
        self.memory = self.bitmap = self.previous = None
        self.size = (0, 0)
        self.origin = (0, 0)
        self.frame = None  # khung cửa sổ lúc chụp: cửa sổ bị kéo đi hay đổi cỡ thì bỏ hiệu ứng
        self.state = None  # None, "hold" hoặc "fade"
        self.held = 0
        self.alpha = 255
        self.started = 0.0
        self.blend = BLENDFUNCTION(0, 0, 255, 0)

    def __call__(self, region=None, when=True):
        self.pending, self.enabled = region, when
        return self

    def __enter__(self):
        region, enabled = self.pending or self.default, self.enabled
        self.pending, self.enabled = None, True
        self.depth += 1
        if self.depth == 1 and enabled:
            self.begin(region)
        return self

    def __exit__(self, *_):
        self.depth -= 1
        if not self.depth and self.state == "hold":
            self.held = 0
            _driver.add(self._frame)

    # ---------- Chụp và phủ ----------

    def _window_frame(self):
        rect = w.RECT()
        GetWindowRect(self.top, byref(rect))
        return rect.left, rect.top, rect.right, rect.bottom

    def _can_run(self, region):
        if _driver is None or not system_animation() or not region.winfo_ismapped():
            return False
        if self.top is None:
            self.top = GetAncestor(self.root.winfo_id(), GA_ROOT)
        return IsWindowVisible(self.top) and not IsIconic(self.top) and region.winfo_width() > 1 and region.winfo_height() > 1

    def begin(self, region):
        if self.state == "hold" and region is self.region:
            self.held = 0  # trang mới chưa vẽ xong mà lại đổi tiếp: ảnh cũ vẫn là thứ người dùng đang thấy
            return
        if not self._can_run(region):
            self.cancel()
            return
        size = (region.winfo_width(), region.winfo_height())
        origin = (region.winfo_rootx(), region.winfo_rooty())
        source = region.winfo_id()
        screen = GetDC(source)
        memory = CreateCompatibleDC(screen)
        bitmap = CreateCompatibleBitmap(screen, *size)
        previous = SelectObject(memory, bitmap)
        BitBlt(memory, 0, 0, *size, screen, 0, 0, SRCCOPY)  # DC của chính cửa sổ: 0,7 ms, còn chụp từ màn hình mất hơn 11 ms
        ReleaseDC(source, screen)
        if self.state == "fade" and region is self.region and size == self.size and origin == self.origin:
            # Đang mờ dở mà đổi tiếp: pha ảnh cũ theo độ mờ hiện tại vào ảnh mới, đúng thứ đang hiện trên màn hình, nên không giật.
            GdiAlphaBlend(memory, 0, 0, *size, self.memory, 0, 0, *size, BLENDFUNCTION(0, 0, self.alpha, 0))
            self._free_bitmap()
        else:
            self.cancel()
        self.memory, self.bitmap, self.previous = memory, bitmap, previous
        self.region, self.size, self.origin = region, size, origin
        self.frame = self._window_frame()
        if self.window is None:
            self.window = CreateWindowExW(WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW, "Static", None, WS_POPUP,
                                          *origin, *size, self.top, None, None, None)
        self.alpha = self.blend.alpha = 255
        UpdateLayeredWindow(self.window, None, byref(w.POINT(*origin)), byref(SIZE(*size)), memory, byref(w.POINT(0, 0)), 0,
                            byref(self.blend), ULW_ALPHA)
        ShowWindow(self.window, SW_SHOWNOACTIVATE)
        self.state = "hold"
        self.held = 0

    def _frame(self, now, _dt):
        if self.state is None:
            return False
        if self._window_frame() != self.frame:
            self.cancel()
            return False
        if self.state == "hold":
            if self.depth:
                return True
            # Mỗi khung chạy hết việc vẽ đang chờ; giữa hai khung Tk nhận nốt sự kiện vẽ của các cửa sổ con vừa hiện.
            self.root.update_idletasks()
            self.held += 1
            if self.held >= HOLD_FRAMES:
                self.state, self.started = "fade", now
            return True
        progress = (now - self.started) / FADE_SECONDS
        if progress >= 1:
            self.cancel()
            return False
        self.alpha = self.blend.alpha = round(255 * (1 - ease_out(progress)))
        UpdateLayeredWindow(self.window, None, None, None, None, None, 0, byref(self.blend), ULW_ALPHA)
        return True

    def _free_bitmap(self):
        if self.memory:
            SelectObject(self.memory, self.previous)
            DeleteObject(self.bitmap)
            DeleteDC(self.memory)
        self.memory = self.bitmap = self.previous = None

    def cancel(self):
        """Bỏ lớp phủ ngay và trả mọi đối tượng GDI."""
        if self.window:
            DestroyWindow(self.window)
            self.window = None
        self._free_bitmap()
        self.state = self.region = None
        if _driver is not None:
            _driver.discard(self._frame)

    @property
    def active(self):
        return self.state is not None

    @property
    def holding(self):
        return self.state == "hold"


# ---------- Pill trượt ----------

class Slide:
    """Một giá trị đi từ a tới b theo đường cong chậm dần, gọi apply(giá trị) ở mỗi khung. Dùng cho pill của thanh bên."""

    def __init__(self, apply, duration):
        self.apply, self.duration = apply, duration
        self.start = self.end = None
        self.elapsed = None
        self.wait = None  # hàm trả về True khi chưa được bắt đầu, như lúc chuyển cảnh còn giữ ảnh cũ

    def run(self, start, end):
        if not system_animation() or _driver is None or start == end:
            self.cancel()
            self.apply(end)
            return
        self.start, self.end, self.elapsed = start, end, None
        _driver.add(self._frame)

    @property
    def active(self):
        return self.end is not None

    def cancel(self):
        self.start = self.end = self.elapsed = None
        if _driver is not None:
            _driver.discard(self._frame)

    def _frame(self, _now, dt):
        if self.end is None:
            return False
        if self.elapsed is None and self.wait is not None and self.wait():
            return True  # đứng ở chỗ cũ cho tới khi nội dung bắt đầu mờ, để hai chuyển động đi cùng nhau
        self.elapsed = 0.0 if self.elapsed is None else self.elapsed + min(dt, STALL_STEP)
        progress = min(self.elapsed / self.duration, 1.0)
        eased = ease_out(progress)
        value = tuple(mix(a, b, eased) for a, b in zip(self.start, self.end))
        self.apply(value)
        if progress >= 1:
            self.start = self.end = self.elapsed = None
            return False
        return True
