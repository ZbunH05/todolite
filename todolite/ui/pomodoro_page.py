"""Trang Pomodoro: đồng hồ lớn, các nút điều khiển, việc đang tập trung, số phiên hôm nay và thời lượng các phiên.

Đồng hồ, dòng trạng thái và các chấm của vòng vẽ trên một Canvas: mỗi giây chỉ đổi chữ của đồng hồ, thanh tiến độ chỉ vẽ lại
khi dài thêm một điểm ảnh. Trạng thái thật nằm trong database (pomodoro.py), trang này chỉ hiện ra và gửi lệnh; agent mới
là nơi chuyển phiên và báo khi hết giờ, nên đóng cửa sổ thì đồng hồ vẫn chạy.
"""
import tkinter as tk
from datetime import datetime, timedelta

import customtkinter as ctk
from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import AppearanceModeTracker
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

from .. import pomodoro
from ..pomodoro import FOCUS, LENGTHS, LONG, PHASE_NAMES, PHASES, SHORT
from ..schedule import countdown_up, humanize
from . import theme
from .shapes import rounded
from .theme import ACCENT, BG, BORDER, CARD, FILL, GREEN, Icon, MUTED, TEXT, TRACK, resolve
from .widgets import (Card, FontCache, GlyphChip, Label, Plain, Scaled, TaskList, draw_week, group_entries, primary_button, scaled,
                      secondary_button, segmented, set_label)

PHASE_LABELS = [PHASE_NAMES[phase] for phase in PHASES]
LENGTH_ROWS = (("pomo_focus", "Tập trung", "phút"), ("pomo_short", "Nghỉ ngắn", "phút"), ("pomo_long", "Nghỉ dài", "phút"),
               ("pomo_rounds", "Nghỉ dài sau", "phiên"))
EMPTY_LIST = "Chưa có việc nào đang mở.\nPomodoro vẫn chạy được mà không cần chọn việc."


def _phase_color(phase):
    return ACCENT if phase == FOCUS else GREEN


class TimerFace(Scaled, tk.Canvas):
    """Mặt đồng hồ: số phút giây thật lớn, dòng trạng thái, các chấm của vòng và việc đang làm."""
    FONTS = {"clock": ("FONT_DISPLAY", 72, 0), "status": ("FONT_SEMIBOLD", 14, 0), "task": ("FONT_TEXT", 13, 0)}
    DOT, DOT_GAP, GAP = 10, 8, 10

    def __init__(self, master):
        super().__init__(master, highlightthickness=0, bd=0)
        self.fonts = FontCache(self.FONTS)
        self.view = None
        self.clock = ""
        self.bind("<Configure>", lambda _: self._paint())
        AppearanceModeTracker.add(lambda _mode: self._paint(), self)
        ScalingTracker.add_widget(self._on_scaling, self)
        self._on_scaling(ScalingTracker.get_widget_scaling(self))

    def _px(self, value):
        return scaled(value, self._scale)

    def _line(self, name):
        return self.fonts.get(name).metrics("linespace")

    def _on_scaling(self, scale, _window=None):
        self._scale = scale
        self.fonts.rescale(scale)
        self.height = self._line("clock") + self._line("status") + self._px(self.GAP) * 2 + self._px(self.DOT) + self._line("task")
        self.configure(height=self.height)
        self._relayout()
        self._paint()

    def show(self, clock, view):
        """view: (trạng thái, màu, việc, số chấm, số chấm đã tô, màu đồng hồ). Chỉ vẽ lại cả mặt khi view đổi."""
        if view != self.view:
            self.view, self.clock = view, clock
            self._paint()
        elif clock != self.clock:
            self.clock = clock
            self.itemconfigure("clock", text=clock)

    def _paint(self):
        self.delete("all")
        self.configure(bg=resolve(CARD))
        width = self.winfo_width()
        if width < 40 or self.view is None:
            return
        status, color, task, dots, filled, clock_color = self.view
        middle, y = width // 2, 0
        self.create_text(middle, y, text=self.clock, font=self.fonts.get("clock"), fill=resolve(clock_color), anchor="n", tags="clock")
        y += self._line("clock")
        self.create_text(middle, y, text=self.fonts.fit("status", status, width), font=self.fonts.get("status"), fill=resolve(color), anchor="n")
        y += self._line("status") + self._px(self.GAP)
        size, gap = self._px(self.DOT), self._px(self.DOT_GAP)
        x = middle - (dots * size + (dots - 1) * gap) // 2
        for index in range(dots):
            rounded(self, x, y, x + size, y + size, size / 2, resolve(color if index < filled else TRACK), resolve(CARD))
            x += size + gap
        y += size + self._px(self.GAP)
        self.create_text(middle, y, text=self.fonts.fit("task", task, width), font=self.fonts.get("task"), fill=resolve(MUTED), anchor="n")


class FocusStats(Scaled, tk.Canvas):
    """Thẻ Hôm nay: số phiên, tổng thời gian tập trung và số phút của 7 ngày qua. Cả thẻ là một Canvas."""
    FONTS = {"title": ("FONT_SEMIBOLD", 16, 0), "number": ("FONT_DISPLAY", 32, 0), "note": ("FONT_TEXT", 13, 0), "small": ("FONT_TEXT", 12, 0)}
    PAD, CHART, GAP = 16, 40, 8

    def __init__(self, master):
        super().__init__(master, highlightthickness=0, bd=0)
        self.fonts = FontCache(self.FONTS)
        self.data = None
        self.bind("<Configure>", lambda _: self._paint())
        AppearanceModeTracker.add(lambda _mode: self._paint(), self)
        ScalingTracker.add_widget(self._on_scaling, self)
        self._on_scaling(ScalingTracker.get_widget_scaling(self))

    def _px(self, value):
        return scaled(value, self._scale)

    def _line(self, name):
        return self.fonts.get(name).metrics("linespace")

    def _on_scaling(self, scale, _window=None):
        self._scale = scale
        self.fonts.rescale(scale)
        self.height = (2 * self._px(self.PAD) + self._line("title") + self._line("number") + self._line("note") + 2 * self._px(self.GAP)
                       + self._px(self.CHART) + self._line("small"))
        self.configure(height=self.height)
        self._relayout()
        self._paint()

    def show(self, data):
        if data != self.data:
            self.data = data
            self._paint()

    def _paint(self):
        self.delete("all")
        self.configure(bg=resolve(BG))
        width = self.winfo_width()
        if width < 40 or self.data is None:
            return
        rounded(self, 0, 0, width, self.height, self._px(theme.RADIUS_CARD), resolve(CARD), resolve(BG), outline=resolve(BORDER))
        pad = self._px(self.PAD)
        x, y, room = pad, pad, width - 2 * pad
        self.create_text(x, y, text="Hôm nay", font=self.fonts.get("title"), fill=resolve(TEXT), anchor="nw")
        y += self._line("title")
        count, minutes = self.data["count"], self.data["minutes"]
        number = self.create_text(x, y, text=str(count), font=self.fonts.get("number"), fill=resolve(ACCENT if count else TEXT), anchor="nw")
        right = self.bbox(number)[2] + self._px(8)
        self.create_text(right, y + self._line("number") - self._line("note") * 1.2, text="phiên tập trung", font=self.fonts.get("note"),
                         fill=resolve(MUTED), anchor="nw")
        y += self._line("number")
        note = f"Tổng {humanize(timedelta(minutes=minutes))}" if minutes else "Chưa có phiên nào xong hôm nay"
        self.create_text(x, y, text=self.fonts.fit("note", note, room), font=self.fonts.get("note"), fill=resolve(MUTED), anchor="nw")
        y += self._line("note") + self._px(self.GAP)
        draw_week(self, x, y, room, self._px(self.CHART), self.data["week"], CARD, self._scale, ())
        y += self._px(self.CHART) + self._px(self.GAP)
        week = sum(value for _day, value in self.data["week"])
        self.create_text(x, y, text="7 ngày qua", font=self.fonts.get("small"), fill=resolve(MUTED), anchor="nw")
        self.create_text(x + room, y, text=humanize(timedelta(minutes=week)) if week else "", font=self.fonts.get("small"),
                         fill=resolve(MUTED), anchor="ne")


class PomodoroPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=BG)
        self.app = app
        self.store = app.store
        self.state = None
        self.config_ = None
        self.progress_step = None
        self.grid_columnconfigure(0, weight=3, uniform="pomodoro")
        self.grid_columnconfigure(1, weight=2, uniform="pomodoro")
        self.grid_rowconfigure(1, weight=1)

        Label(self, text="Pomodoro", font=theme.display(24), text_color=TEXT, anchor="w", height=36).grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(18, 10))
        main = Plain(self)
        main.grid(row=1, column=0, sticky="nsew", padx=(24, 6), pady=(0, 20))
        side = Plain(self)
        side.grid(row=1, column=1, sticky="nsew", padx=(6, 24), pady=(0, 20))
        self._build_timer(main)
        Label(main, text="Chọn việc để tập trung", font=theme.semibold(16), text_color=TEXT, anchor="w", height=26).pack(
            fill="x", padx=4, pady=(12, 0))
        self.task_list = TaskList(main, app, self._link, app.open_task, EMPTY_LIST)
        self.task_list.pack(fill="both", expand=True)
        self.stats = FocusStats(side)
        self.stats.pack(fill="x")
        self._build_lengths(side)

    # ---------- Dựng ----------

    def _build_timer(self, master):
        card = Card(master)
        card.pack(fill="x")
        self.phases = segmented(card, PHASE_LABELS, self._choose, text_color_disabled=MUTED)  # khoá khi đồng hồ chạy nhưng vẫn đọc rõ
        self.phases.pack(pady=(14, 6))
        self.face = TimerFace(card)
        self.face.pack(fill="x", padx=16)
        self.progress = ctk.CTkProgressBar(card, height=6, corner_radius=3, fg_color=TRACK, progress_color=ACCENT)
        self.progress.pack(fill="x", padx=40, pady=(12, 14))
        self.progress.bind("<Configure>", lambda _: setattr(self, "progress_step", None), add="+")
        buttons = Plain(card)
        buttons.pack(fill="x", padx=40, pady=(0, 16))
        self.main_button = primary_button(buttons, "Bắt đầu", self._toggle)
        self.main_button.pack(side="left", fill="x", expand=True)
        secondary_button(buttons, "Bỏ qua", self._skip, width=84).pack(side="left", padx=(8, 0))
        secondary_button(buttons, "Đặt lại", self._stop, width=84).pack(side="left", padx=(8, 0))

    def _build_lengths(self, master):
        card = Card(master)
        card.pack(fill="x", pady=(10, 0))
        Label(card, text="Thời lượng", font=theme.semibold(16), text_color=TEXT, anchor="w", height=26).pack(fill="x", padx=16, pady=(12, 4))
        self.length_labels = {}
        for key, name, unit in LENGTH_ROWS:
            row = Plain(card)
            row.pack(fill="x", padx=16, pady=3)
            Label(row, text=name, font=theme.text(14), text_color=TEXT, anchor="w", height=28).pack(side="left")
            GlyphChip(row, Icon.ADD, lambda key=key: self._step(key, 1), width=30).pack(side="right")
            value = Label(row, text="", font=theme.text(13), text_color=TEXT, width=72, height=28)
            value.pack(side="right")
            GlyphChip(row, Icon.REMOVE, lambda key=key: self._step(key, -1), width=30).pack(side="right")
            self.length_labels[key] = (value, unit)
        self.switches = {}
        for key, name in (("pomo_auto_break", "Tự bắt đầu giờ nghỉ"), ("pomo_auto_focus", "Tự bắt đầu phiên tập trung")):
            row = Plain(card)
            row.pack(fill="x", padx=16, pady=(6, 0))
            Label(row, text=name, font=theme.text(14), text_color=TEXT, anchor="w", height=28).pack(side="left")
            switch = ctk.CTkSwitch(row, text="", width=44, progress_color=FILL, fg_color=theme.SWITCH_OFF, button_color=theme.SWITCH_KNOB,
                                   button_hover_color=theme.SWITCH_KNOB, command=lambda key=key: self._set_flag(key))
            switch.pack(side="right")
            self.switches[key] = switch
        note = Label(card, text="Hết phiên thì Windows báo, đóng cửa sổ đồng hồ vẫn chạy.", font=theme.text(12), text_color=MUTED, anchor="w",
                     justify="left", height=18, elastic=True)
        note.pack(fill="x", padx=16, pady=(8, 14))
        card.bind("<Configure>", lambda event: set_label(note, wraplength=round(event.width / ScalingTracker.get_widget_scaling(self)) - 34),
                  add="+")

    # ---------- Dữ liệu ----------

    def refresh(self, now):
        self.state, self.config_ = pomodoro.read(self.store), pomodoro.config(self.store)
        state = self.state
        task = self.store.get_task(state.task_id) if state.task_id else None
        self.task_title = (task["title"] + (" (đã xong)" if task["done_at"] else "")) if task else ""
        # Widget CustomTkinter vẽ lại cả canvas mỗi lần configure, kể cả khi giá trị không đổi: chỉ đổi thứ thật sự đổi.
        if self.phases.get() != PHASE_NAMES[state.phase]:
            self.phases.set(PHASE_NAMES[state.phase])
        locked = "disabled" if pomodoro.running(state) or state.left is not None else "normal"
        if self.phases.cget("state") != locked:
            self.phases.configure(state=locked)
        action = "Tạm dừng" if pomodoro.running(state) else "Tiếp tục" if state.left is not None else "Bắt đầu"
        if self.main_button.cget("text") != action:
            self.main_button.configure(text=action)
        if self.progress.cget("progress_color") != _phase_color(state.phase):
            self.progress.configure(progress_color=_phase_color(state.phase))
            self.progress_step = None
        for key, (label, unit) in self.length_labels.items():
            set_label(label, text=f"{pomodoro.setting_number(self.store, key)} {unit}")
        for key, switch in self.switches.items():
            wanted = self.store.setting(key) == "1"
            if wanted and switch.get() != 1:  # select và deselect không gọi lại lệnh như toggle
                switch.select()
            elif not wanted and switch.get() == 1:
                switch.deselect()
        self.stats.show(self.store.focus_stats(now))
        self.task_list.set_entries(group_entries(self.store.list_tasks("all", now), now, "all"))
        self.task_list.select(state.task_id)
        self.tick(now)

    def _view(self):
        state, cfg = self.state, self.config_
        running, paused = pomodoro.running(state), state.left is not None
        name = PHASE_NAMES[state.phase]
        if state.phase == FOCUS:
            where = f"phiên {state.round % cfg.rounds + 1}/{cfg.rounds}"
            status = f"Tạm dừng · {where}" if paused else f"{name} · {where}" if running else f"Sẵn sàng tập trung · {where}"
        else:
            rest = "đứng dậy vươn vai, uống nước" if state.phase == SHORT else f"xong {cfg.rounds} phiên, nghỉ cho đã"
            status = f"Tạm dừng · {name.lower()}" if paused else f"{name} · {rest}" if running else f"Sẵn sàng {name.lower()}"
        task = f"Việc: {self.task_title}" if self.task_title else "Chưa chọn việc · bấm một việc bên dưới để gắn"
        filled = cfg.rounds if state.phase == LONG else state.round % cfg.rounds
        return (status, MUTED if paused else _phase_color(state.phase), task, cfg.rounds, filled, MUTED if paused else TEXT)

    def tick(self, now):
        if self.state is None:
            return
        left = pomodoro.seconds_left(self.state, self.config_, now)
        self.face.show(countdown_up(timedelta(seconds=left)), self._view())
        total = pomodoro.minutes_of(self.config_, self.state.phase) * 60
        value = min(max(left / total, 0), 1)
        step = round(value * self.progress.winfo_width())
        if step != self.progress_step:  # phiên 25 phút chỉ dịch 1 điểm ảnh mỗi vài giây, không vẽ lại thanh mỗi giây
            self.progress_step = step
            self.progress.set(value)

    # ---------- Lệnh ----------

    def _act(self, action, *args):
        action(self.store, *args)
        self.app.changed()  # báo agent: hẹn giờ thức đúng lúc hết phiên, cập nhật đồng hồ nổi

    def _toggle(self):
        self._act(pomodoro.pause if pomodoro.running(pomodoro.read(self.store)) else pomodoro.start, datetime.now())

    def _skip(self):
        self._act(pomodoro.skip)

    def _stop(self):
        self._act(pomodoro.stop)

    def _choose(self, label):
        phase = PHASES[PHASE_LABELS.index(label)]
        if self.state and phase != self.state.phase:
            self._act(pomodoro.choose, phase)

    def _link(self, task_id):
        """Bấm một việc để gắn vào Pomodoro, bấm lại việc đang gắn để bỏ gắn."""
        self._act(pomodoro.link, None if self.state and task_id == self.state.task_id else task_id)

    def _step(self, key, direction):
        _default, low, high, step = LENGTHS[key]
        value = min(max(pomodoro.setting_number(self.store, key) + direction * step, low), high)
        self.store.set_setting(key, value)
        self.app.changed()

    def _set_flag(self, key):
        self.store.set_setting(key, "1" if self.switches[key].get() == 1 else "0")
        self.app.changed()
