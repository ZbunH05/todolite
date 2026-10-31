"""Panel chi tiết task. Mọi thay đổi tự lưu, không có nút Save."""
from datetime import date, datetime, timedelta

import customtkinter as ctk

from ..db import task_tag_names
from ..quickparse import parse_when
from ..schedule import ALL_DAY_TIME, RECUR_LABELS, REMIND_CHOICES, block_window, day_label, from_text, parse_offsets, to_text, when_label
from . import theme
from .theme import ACCENT, BORDER, CARD_HOVER, FILL, FILL_HOVER, GREEN, Icon, MUTED, ON_FILL, RED, TEXT, TRACK
from .widgets import Card, Chip, DatePicker, IconButton, TagPicker, field, primary_button, secondary_button, segmented, set_text

REMIND_LABELS = {5: "5p", 15: "15p", 30: "30p", 60: "1 giờ", 1440: "1 ngày"}
RECUR_CHOICES = {"Không": "", "Ngày": "daily", "T2–T6": "weekdays", "Tuần": "weekly", "Tháng": "monthly"}
RECUR_BY_RULE = {rule: label for label, rule in RECUR_CHOICES.items()}
BLOCK_PRESETS = (25, 50, 90)
DELETE_CONFIRM_MS = 3000


class TaskEditor(Card):
    def __init__(self, master, app):
        super().__init__(master, width=372)
        self.app = app
        self.store = app.store
        self.task_id = None
        self.task = None
        self.loading = False
        self.notes_timer = None
        self.delete_armed = False
        self.block_minutes = BLOCK_PRESETS[0]
        self.pack_propagate(False)
        self._build()

    # ---------- Dựng giao diện ----------

    def _build(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 0))
        self.heading = ctk.CTkLabel(top, text="Chi tiết", font=theme.semibold(13), text_color=MUTED, anchor="w")
        self.heading.pack(side="left")
        IconButton(top, Icon.CLOSE, self.app.close_editor, size=28).pack(side="right")

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=TRACK,
                                           scrollbar_button_hover_color=MUTED)
        self.body.pack(fill="both", expand=True, padx=(8, 4), pady=(0, 6))

        self.title_entry = ctk.CTkEntry(self.body, height=38, border_width=0, fg_color="transparent", text_color=TEXT,
                                        font=theme.semibold(17), placeholder_text="Tên việc")
        self.title_entry.pack(fill="x", padx=(0, 6))
        self.title_entry.bind("<FocusOut>", self._save_title)
        self.title_entry.bind("<Return>", self._save_title)

        self._build_deadline()
        self._build_reminders()
        self._build_options()
        self._build_block()
        self._build_checkpoints()
        self._build_notes()
        self._build_footer()

    def _section(self, title):
        frame = ctk.CTkFrame(self.body, fg_color="transparent")
        frame.pack(fill="x", padx=(6, 8), pady=(10, 0))
        if title:
            ctk.CTkLabel(frame, text=title, font=theme.text(12), text_color=MUTED, anchor="w", height=20).pack(fill="x")
        return frame

    def _build_deadline(self):
        section = self._section("Hạn chót")
        row = ctk.CTkFrame(section, fg_color="transparent")
        row.pack(fill="x", pady=(2, 0))
        self.due_entry = field(row, placeholder_text="vd: mai 9h, t6 14:00, 15/11")
        self.due_entry.pack(side="left", fill="x", expand=True)
        self.due_entry.bind("<FocusOut>", self._save_due)
        self.due_entry.bind("<Return>", self._save_due)
        self.calendar_button = IconButton(row, Icon.CALENDAR, self._open_calendar, size=34)
        self.calendar_button.pack(side="left", padx=(4, 0))
        chips = ctk.CTkFrame(section, fg_color="transparent")
        chips.pack(fill="x", pady=(6, 0))
        for label, days in (("Hôm nay", 0), ("Ngày mai", 1), ("Tuần sau", 7)):
            Chip(chips, label, lambda d=days: self._set_due_days(d), width=64).pack(side="left", padx=(0, 6))
        Chip(chips, "Bỏ hạn", self._clear_due, width=52).pack(side="left")

    def _build_reminders(self):
        section = self._section("Nhắc trước hạn")
        row = ctk.CTkFrame(section, fg_color="transparent")
        row.pack(fill="x", pady=(2, 0))
        self.remind_chips = {}
        for minutes in REMIND_CHOICES:
            chip = Chip(row, REMIND_LABELS[minutes], lambda m=minutes: self._toggle_remind(m), width=48)
            chip.pack(side="left", padx=(0, 6))
            self.remind_chips[minutes] = chip

    def _build_options(self):
        section = self._section("Tag")
        self.tags = TagPicker(section, self.app, self._save_tags)
        self.tags.pack(fill="x", pady=(2, 0))
        section = self._section("Lặp lại")
        self.recur = segmented(section, list(RECUR_CHOICES), self._save_recur, dynamic_resizing=False)
        self.recur.pack(fill="x", pady=(2, 0))
        section = self._section("Ưu tiên")
        self.priority = segmented(section, list(theme.PRIORITY_LABELS), self._save_priority, dynamic_resizing=False)
        self.priority.pack(fill="x", pady=(2, 0))

    def _build_block(self):
        section = self._section("Khối thời gian (time-block)")
        self.block_status = ctk.CTkLabel(section, text="", font=theme.text(12), text_color=ACCENT, anchor="w", height=18)
        self.block_row = row = ctk.CTkFrame(section, fg_color="transparent")
        row.pack(fill="x", pady=(2, 0))
        self.block_start = field(row, placeholder_text="Bắt đầu: 14h, mai 9h", width=132)
        self.block_start.pack(side="left")
        self.block_start.bind("<FocusOut>", self._save_block_start)
        self.block_start.bind("<Return>", self._save_block_start)
        self.block_chips = {}
        for minutes in BLOCK_PRESETS:
            chip = Chip(row, f"{minutes}p", lambda m=minutes: self._pick_block_minutes(m), width=42)
            chip.pack(side="left", padx=(6, 0))
            self.block_chips[minutes] = chip
        actions = ctk.CTkFrame(section, fg_color="transparent")
        actions.pack(fill="x", pady=(6, 0))
        self.start_button = primary_button(actions, "Bắt đầu ngay", self._start_block, width=118, height=30)
        self.start_button.pack(side="left")
        self.clear_block_button = secondary_button(actions, "Xoá khối", self._clear_block, width=76, height=30)

    def _build_checkpoints(self):
        section = self._section("")
        header = ctk.CTkFrame(section, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(header, text="Checkpoint", font=theme.text(12), text_color=MUTED, anchor="w", height=20).pack(side="left")
        self.checkpoint_count = ctk.CTkLabel(header, text="", font=theme.text(12), text_color=MUTED, height=20)
        self.checkpoint_count.pack(side="right")
        self.checkpoint_bar = ctk.CTkProgressBar(section, height=6, corner_radius=3, progress_color=ACCENT, fg_color=TRACK)
        self.checkpoint_bar.pack(fill="x", pady=(2, 4))
        self.checkpoint_rows = ctk.CTkFrame(section, fg_color="transparent", height=1)
        self.new_checkpoint = field(section, placeholder_text="+ Thêm checkpoint, Enter để lưu")
        self.new_checkpoint.pack(fill="x", pady=(4, 0))
        self.new_checkpoint.bind("<Return>", self._add_checkpoint)

    def _build_notes(self):
        section = self._section("Ghi chú")
        self.notes = ctk.CTkTextbox(section, height=84, corner_radius=8, border_width=1, border_color=BORDER,
                                    fg_color=theme.FIELD, text_color=TEXT, font=theme.text(13), wrap="word",
                                    activate_scrollbars=False)  # thanh cuộn của CTkTextbox chậm và có vòng dò nền
        self.notes.pack(fill="x", pady=(2, 0))
        self.notes.bind("<KeyRelease>", self._notes_changed)
        self.notes.bind("<FocusOut>", self._flush_notes)

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=(0, 12))
        self.done_button = primary_button(footer, "Hoàn thành", self._toggle_done)
        self.done_button.pack(side="left", fill="x", expand=True)
        self.delete_button = secondary_button(footer, "Xoá", self._delete, width=84, text_color=RED)
        self.delete_button.pack(side="left", padx=(8, 0))

    # ---------- Nạp dữ liệu ----------

    def flush(self):
        """Lưu nốt phần đang gõ dở, gọi trước khi đổi task hoặc đóng cửa sổ."""
        self._save_title()
        self._flush_notes()

    def load(self, task_id):
        self.flush()
        self.task_id = task_id
        self.reload(full=True)

    def reload(self, full=False):
        """Làm mới từ DB. Khi đang gõ dở (agent đổi dữ liệu ngầm), chỉ cập nhật phần không gõ."""
        self.task = self.store.get_task(self.task_id) if self.task_id else None
        if self.task is None:
            self.app.close_editor()
            return
        self.loading = True
        task = self.task
        focused = self.focus_get()
        if full or focused is not self.title_entry._entry:
            set_text(self.title_entry, task["title"])
        if full or focused is not self.due_entry._entry:
            set_text(self.due_entry, when_label(task["due_at"], task["all_day"], datetime.now()) if task["due_at"] else "")
            self.due_entry.configure(border_color=BORDER)
        self.tags.set_selected(task_tag_names(task))
        if full or focused is not self.block_start._entry:
            set_text(self.block_start, self._block_start_label())
        if full or focused is not self.notes._textbox:
            self.notes.delete("1.0", "end")
            self.notes.insert("1.0", task["notes"])
        active = parse_offsets(task["remind"])
        for minutes, chip in self.remind_chips.items():
            chip.set_active(minutes in active)
        self.recur.set(RECUR_BY_RULE.get(task["recur"].split(":")[0], "Không"))
        self.priority.set(theme.PRIORITY_LABELS[task["priority"]])
        if task["block_minutes"]:
            self.block_minutes = task["block_minutes"]
        self._refresh_block_ui()
        self._render_checkpoints()
        self.done_button.configure(text="Mở lại việc" if task["done_at"] else "Hoàn thành")
        self._disarm_delete()
        self.loading = False

    def _block_start_label(self):
        return when_label(self.task["block_start"][:16], 0, datetime.now()) if self.task["block_start"] else ""

    def _refresh_block_ui(self):
        for minutes, chip in self.block_chips.items():
            chip.set_active(minutes == self.block_minutes)
        window = block_window(self.task)
        if window:
            now = datetime.now()
            start, end = window
            if start <= now < end:
                status = f"Đang chạy, kết thúc lúc {end:%H:%M}"
            elif end <= now:
                status = f"Đã kết thúc lúc {end:%H:%M}"
            else:
                status = f"{day_label(start.date(), now.date())} {start:%H:%M}–{end:%H:%M}"
            self.block_status.configure(text=status)
            self.block_status.pack(fill="x", pady=(2, 0), before=self.block_row)
            self.clear_block_button.pack(side="left", padx=(6, 0))
        else:
            self.block_status.pack_forget()
            self.clear_block_button.pack_forget()

    def _render_checkpoints(self):
        for child in self.checkpoint_rows.winfo_children():
            child.destroy()
        rows = self.store.checkpoints(self.task_id)
        for row in rows:
            self._checkpoint_row(row)
        # Khung rỗng không tự co lại, phải ẩn đi để ô thêm checkpoint nằm ngay dưới tiêu đề.
        if rows:
            self.checkpoint_rows.pack(fill="x", before=self.new_checkpoint)
        else:
            self.checkpoint_rows.pack_forget()
        total = len(rows)
        finished = sum(row["done"] for row in rows)
        self.checkpoint_count.configure(text=f"{finished}/{total}" if total else "")
        if total:
            self.checkpoint_bar.configure(progress_color=GREEN if finished == total else ACCENT)
            self.checkpoint_bar.set(finished / total)
            self.checkpoint_bar.pack(fill="x", pady=(2, 4), before=self.checkpoint_rows)
        else:
            self.checkpoint_bar.pack_forget()

    def _checkpoint_row(self, row):
        frame = ctk.CTkFrame(self.checkpoint_rows, fg_color="transparent", height=30)
        frame.pack(fill="x")
        box = ctk.CTkCheckBox(frame, text=row["title"], width=20, checkbox_width=18, checkbox_height=18, corner_radius=5,
                              border_width=2, border_color=MUTED, fg_color=FILL, hover_color=FILL_HOVER, checkmark_color=ON_FILL,
                              text_color=MUTED if row["done"] else TEXT, font=theme.text(13),
                              command=lambda: self._toggle_checkpoint(row["id"], box))
        if row["done"]:
            box.select()
        box.pack(side="left", fill="x", expand=True, pady=2)
        box.bind("<Double-Button-1>", lambda _event: self._rename_checkpoint(frame, row))
        IconButton(frame, Icon.CLOSE, lambda: self._delete_checkpoint(row["id"]), size=24).pack(side="right")

    # ---------- Lưu thay đổi ----------

    def _save(self, **fields):
        if self.task_id and not self.loading:
            self.store.update_task(self.task_id, **fields)
            self.app.changed(reload_editor=False)
            self.task = self.store.get_task(self.task_id)

    def _save_title(self, _event=None):
        value = self.title_entry.get()
        if self.task and value.strip() and value != self.task["title"]:
            self._save(title=value)

    def _save_tags(self, names):
        if self.task_id:
            self.store.set_task_tags(self.task_id, names)
            self.app.changed(reload_editor=False)
            self.task = self.store.get_task(self.task_id)

    def _save_due(self, _event=None):
        if not self.task:
            return
        value = self.due_entry.get().strip()
        current = when_label(self.task["due_at"], self.task["all_day"], datetime.now()) if self.task["due_at"] else ""
        if value == current:
            self.due_entry.configure(border_color=BORDER)
            return
        if not value:
            self._clear_due()
            return
        parsed = parse_when(value)
        if parsed is None:
            self.due_entry.configure(border_color=RED)
            return
        self.due_entry.configure(border_color=BORDER)
        self._apply_due(*parsed)

    def _apply_due(self, due_at, all_day):
        self._save(due_at=due_at, all_day=all_day, snooze_until=None)
        set_text(self.due_entry, when_label(due_at, all_day, datetime.now()))

    def _set_due_days(self, days):
        self._pick_date(date.today() + timedelta(days=days))

    def _pick_date(self, picked):
        moment = self.task["due_at"][11:16] if self.task["due_at"] and not self.task["all_day"] else None
        self._apply_due(f"{picked.isoformat()} {moment or ALL_DAY_TIME}", 0 if moment else 1)

    def _clear_due(self):
        self._save(due_at=None, all_day=0, snooze_until=None)
        set_text(self.due_entry, "")

    def _open_calendar(self):
        if self.task:
            current = from_text(self.task["due_at"]).date() if self.task["due_at"] else None
            DatePicker(self.calendar_button, current, self._pick_date)

    def _toggle_remind(self, minutes):
        chip = self.remind_chips[minutes]
        chip.set_active(not chip.active)
        chosen = [str(value) for value, item in self.remind_chips.items() if item.active]
        self._save(remind=",".join(chosen))

    def _save_recur(self, label):
        rule = RECUR_CHOICES[label]
        fields = {"recur": rule}
        if rule and not self.task["due_at"]:
            fields |= {"due_at": f"{date.today().isoformat()} {ALL_DAY_TIME}", "all_day": 1}
        self._save(**fields)
        if "due_at" in fields:
            self.reload()

    def _save_priority(self, label):
        self._save(priority=theme.PRIORITY_LABELS.index(label))

    def _notes_changed(self, _event=None):
        if self.notes_timer:
            self.after_cancel(self.notes_timer)
        self.notes_timer = self.after(700, self._flush_notes)

    def _flush_notes(self, _event=None):
        if self.notes_timer:
            self.after_cancel(self.notes_timer)
            self.notes_timer = None
        if self.task:
            value = self.notes.get("1.0", "end-1c")
            if value != self.task["notes"]:
                self._save(notes=value)

    # ---------- Khối thời gian ----------

    def _pick_block_minutes(self, minutes):
        self.block_minutes = minutes
        if self.task["block_start"]:
            self._save(block_minutes=minutes)
        self._refresh_block_ui()

    def _save_block_start(self, _event=None):
        if not self.task:
            return
        value = self.block_start.get().strip()
        if value == self._block_start_label():
            return
        if not value:
            self._clear_block()
            return
        parsed = parse_when(value)
        if parsed is None or parsed[1]:
            self.block_start.configure(border_color=RED)
            return
        self.block_start.configure(border_color=BORDER)
        self._save(block_start=parsed[0], block_minutes=self.block_minutes)
        self.reload(full=False)

    def _start_block(self):
        self.store.start_block(self.task_id, self.block_minutes)
        self.app.changed()
        set_text(self.block_start, self._block_start_label())

    def _clear_block(self):
        self.store.end_block(self.task_id)
        self.app.changed()
        set_text(self.block_start, "")

    # ---------- Checkpoint ----------

    def _add_checkpoint(self, _event=None):
        if self.store.add_checkpoint(self.task_id, self.new_checkpoint.get()):
            set_text(self.new_checkpoint, "")
            self._after_checkpoint()
        return "break"

    def _toggle_checkpoint(self, checkpoint_id, box):
        self.store.set_checkpoint(checkpoint_id, box.get() == 1)
        self._after_checkpoint()

    def _delete_checkpoint(self, checkpoint_id):
        self.store.delete_checkpoint(checkpoint_id)
        self._after_checkpoint()

    def _rename_checkpoint(self, frame, row):
        for child in frame.winfo_children():
            child.pack_forget()
        entry = field(frame, height=28)
        entry.insert(0, row["title"])
        entry.pack(fill="x", expand=True, pady=1)
        entry.focus_set()

        def finish(_event=None):
            self.store.rename_checkpoint(row["id"], entry.get())
            self.after_idle(self._after_checkpoint)

        entry.bind("<Return>", finish)
        entry.bind("<FocusOut>", finish)
        entry.bind("<Escape>", lambda _: self.after_idle(self._render_checkpoints))

    def _after_checkpoint(self):
        self._render_checkpoints()
        self.app.changed(reload_editor=False)
        self.task = self.store.get_task(self.task_id)

    # ---------- Hành động ----------

    def _toggle_done(self):
        self.app.toggle_task(self.task)

    def _delete(self):
        if not self.delete_armed:
            self.delete_armed = True
            self.delete_button.configure(text="Chắc chứ?", fg_color=RED, hover_color=RED, text_color="#FFFFFF")
            self.after(DELETE_CONFIRM_MS, self._disarm_delete)
            return
        task_id, title = self.task_id, self.task["title"]
        self.task_id = None
        self.store.delete_task(task_id)
        self.app.close_editor()
        self.app.changed(reload_editor=False)
        self.app.snackbar.show(f"Đã xoá: {title}")

    def _disarm_delete(self):
        if self.delete_armed:
            self.delete_armed = False
            self.delete_button.configure(text="Xoá", fg_color="transparent", hover_color=CARD_HOVER, text_color=RED)
