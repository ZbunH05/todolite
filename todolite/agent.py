"""Tiến trình nền: icon khay, lịch nhắc, thông báo, phím tắt toàn cục.

Không dùng vòng lặp sleep: tiến trình nằm yên trong GetMessageW (0% CPU) và chỉ thức
dậy đúng lúc có việc, nhờ timer đặt tới mốc nhắc gần nhất. Giao diện báo "dữ liệu đổi"
bằng một PostMessage để agent tính lại lịch ngay.
"""
from ctypes import byref, sizeof
from ctypes import wintypes as w
from datetime import datetime, timedelta

from . import APP_ID, APP_NAME, integration, schedule, toast
from .db import Store
from .paths import ICON_ALERT_PATH, ICON_PATH, ROOT, RUN_SCRIPT, SANDBOX, log, pythonw
from .popups import PillItem, QuickAdd, ReminderCard, TimerPill
from .vault import unprotect
from .win32 import *  # noqa: F403

TIMER_TICK = 1
TIMER_TRIM = 2
TRIM_DELAY_MS = 1500  # lúc luồng nghe báo thì nó còn đang dựng kết nối, chạm lại vài MB; đợi nó nằm yên trong WinHTTP
HOTKEY_QUICK_ADD = 1
MAX_SLEEP = timedelta(minutes=5)  # lưới an toàn: agent vẫn tự rà soát định kỳ
MAX_INDIVIDUAL_ALERTS = 3
BRIEF_RETRY = timedelta(minutes=5)  # lỗi mạng thì thử lại sau chừng này
REMIND_RETRY = timedelta(minutes=2)  # tiến trình gửi nhắc hạn chưa gửi được thì mở lại sau chừng này


def _earliest(*moments):
    return min((moment for moment in moments if moment), default=None)

MENU_OPEN, MENU_QUICK_ADD, MENU_SUMMARY, MENU_AUTOSTART, MENU_QUIT = 1, 2, 3, 4, 5


class Agent:
    def __init__(self, autostarted=False, open_ui=False):
        self.store = Store(cache_kb=128)
        self.pending_summary = autostarted
        self.open_ui_on_start = open_ui
        self.first_tick = True
        self.locked = False
        self.tray_added = False
        self.hotkey_on = False
        self.icon_name = ""
        self.icons = {}
        self.resumed = False
        self.brief_start_day = None  # ngày PC bật gần nhất, tính cả lúc mở nắp máy sau khi ngủ
        self.brief_spawned_at = None
        self.remind_spawned_at = None
        self.pomo_notice = self.store.setting("pomo_notice")  # thông báo chuyển phiên đã hiện; cái cũ từ lần chạy trước thì thôi
        self.listener = None  # chỉ tạo khi cần: người không dùng bot không tốn gì cho phần mạng
        self.listener_wanted = None
        self.listener_problem = ""
        self._procedure = WNDPROC(self._window_proc)
        self.taskbar_created = RegisterWindowMessageW("TaskbarCreated")

    # ---------- Vòng đời ----------

    def run(self):
        SetProcessDpiAwarenessContext(DPI_PER_MONITOR_V2)
        SetAppUserModelID(APP_ID)
        if not SANDBOX:
            integration.register_app()
            integration.refresh_autostart()
        register_window_class(AGENT_WINDOW_CLASS, self._procedure)
        self.hwnd = CreateWindowExW(WS_EX_TOOLWINDOW, AGENT_WINDOW_CLASS, APP_NAME, WS_POPUP, 0, 0, 0, 0,
                                    None, None, HINSTANCE, None)
        self.quick = QuickAdd(self)
        self.pill = TimerPill(self)
        self.card = ReminderCard(self)
        register_session_notification(self.hwnd)
        self._add_tray()
        self.tick()
        if self.open_ui_on_start:
            self.open_ui()
        self._message_loop()

    def _message_loop(self):
        message = w.MSG()
        while GetMessageW(byref(message), None, 0, 0) > 0:
            try:
                if self.quick.handle_key(message):
                    continue
            except Exception as error:
                self.report(error)  # lỗi lẻ không được phép giết tiến trình nền
            TranslateMessage(byref(message))
            DispatchMessageW(byref(message))

    def _sync_hotkey(self):
        wanted = self.store.setting("hotkey") == "1"
        if wanted and not self.hotkey_on:
            self.hotkey_on = bool(RegisterHotKey(self.hwnd, HOTKEY_QUICK_ADD, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_T))
            if not self.hotkey_on and self.first_tick:
                log("Không đăng ký được Ctrl+Alt+T: phím đang bị ứng dụng khác dùng")
        elif self.hotkey_on and not wanted:
            UnregisterHotKey(self.hwnd, HOTKEY_QUICK_ADD)
            self.hotkey_on = False

    def _sync_listener(self, now):
        """Nghe tin nhắn Telegram khi đã cài xong bot. So bản token đã mã hoá để khỏi giải mã ở mỗi lần tính lịch."""
        token = self.store.setting("telegram_token")
        ready = self.store.setting("telegram_inbox") == "1" and token and self.store.setting("telegram_chat_id")
        wanted = (token, self.store.setting("telegram_api_url")) if ready else None
        if wanted != self.listener_wanted:
            self.listener_wanted = wanted
            if wanted and not self.listener:
                from .listener import Listener
                self.listener = Listener(lambda: PostMessageW(self.hwnd, WM_APP_TRIM, 0, 0))
            if wanted and not self.store.setting("telegram_inbox_since"):
                self.store.set_setting("telegram_inbox_since", int(now.timestamp()))
            if self.listener:
                self.listener.listen((unprotect(token), wanted[1]) if wanted else None)
        problem = self.listener.problem if self.listener else ""
        if problem != self.listener_problem:
            self.listener_problem = problem
            if problem:
                self.store.set_setting("telegram_status", f"{now:%H:%M %d/%m}: Chưa nhận được tin nhắn. {problem}")

    def report(self, error):
        import traceback
        log("".join(traceback.format_exception(error)))

    def quit(self):
        self._remove_tray()
        PostQuitMessage(0)

    # ---------- Khay hệ thống ----------

    def _icon(self, path):
        if path not in self.icons:
            width, height = GetSystemMetrics(SM_CXSMICON), GetSystemMetrics(SM_CYSMICON)
            self.icons[path] = LoadImageW(None, path, IMAGE_ICON, width, height, LR_LOADFROMFILE)
        return self.icons[path]

    def _tray_data(self, flags):
        data = NOTIFYICONDATAW()
        data.cbSize = sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = 1
        data.uFlags = flags
        return data

    def _add_tray(self):
        data = self._tray_data(NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP)
        data.uCallbackMessage = WM_APP_TRAY
        data.hIcon = self._icon(ICON_PATH)
        data.szTip = APP_NAME
        self.tray_added = bool(Shell_NotifyIconW(NIM_ADD, byref(data)))
        if self.tray_added:
            data.uVersion = NOTIFYICON_VERSION_4
            Shell_NotifyIconW(NIM_SETVERSION, byref(data))
            self.icon_name = ""
        else:
            log("Chưa thêm được icon khay (Explorer chưa sẵn sàng?), sẽ thử lại")

    def _remove_tray(self):
        if self.tray_added:
            Shell_NotifyIconW(NIM_DELETE, byref(self._tray_data(0)))
            self.tray_added = False

    def _update_tray(self, tooltip, icon_path):
        if not self.tray_added:
            self._add_tray()
            if not self.tray_added:
                return
        flags = NIF_TIP | NIF_SHOWTIP | (NIF_ICON if icon_path != self.icon_name else 0)
        data = self._tray_data(flags)
        data.szTip = tooltip[:127]
        data.hIcon = self._icon(icon_path)
        Shell_NotifyIconW(NIM_MODIFY, byref(data))
        self.icon_name = icon_path

    def _balloon(self, title, text):
        """Dự phòng khi toast WinRT lỗi: thông báo kiểu cũ qua khay hệ thống."""
        data = self._tray_data(NIF_INFO)
        data.szInfoTitle = title[:63]
        data.szInfo = text[:255]
        data.dwInfoFlags = NIIF_USER
        data.hBalloonIcon = self._icon(ICON_PATH)
        Shell_NotifyIconW(NIM_MODIFY, byref(data))

    def _show_menu(self, x, y):
        autostart = integration.autostart_enabled()
        items = [(MENU_OPEN, f"Mở {APP_NAME}", False, True),
                 (MENU_QUICK_ADD, "Thêm nhanh…\tCtrl+Alt+T", False, True),
                 (0, "", False, True),
                 (MENU_SUMMARY, "Gửi lại tóm tắt hôm nay", False, True),
                 (MENU_AUTOSTART, "Khởi động cùng Windows", autostart, True),
                 (0, "", False, True),
                 (MENU_QUIT, "Thoát", False, True)]
        chosen = show_context_menu(self.hwnd, items, x, y)
        if chosen == MENU_OPEN:
            self.open_ui()
        elif chosen == MENU_QUICK_ADD:
            self.quick.show()
        elif chosen == MENU_SUMMARY:
            self.send_summary(datetime.now())
        elif chosen == MENU_AUTOSTART:
            integration.set_autostart(not autostart)
        elif chosen == MENU_QUIT:
            self.quit()

    # ---------- Giao diện ----------

    def open_ui(self):
        hwnd = FindWindowW(UI_WINDOW_CLASS, APP_NAME)
        AllowSetForegroundWindow(ASFW_ANY)
        if hwnd:
            if IsIconic(hwnd):
                ShowWindow(hwnd, SW_RESTORE)
            SetForegroundWindow(hwnd)
        else:
            ShellExecuteW(None, "open", pythonw(), f'"{RUN_SCRIPT}" --ui', ROOT, SW_SHOWNORMAL)

    def open_task(self, task_id):
        self.store.set_setting("ui_request", f"task:{task_id}")
        self.open_ui()

    def open_page(self, key):
        self.store.set_setting("ui_request", f"page:{key}")
        self.open_ui()

    # ---------- Lịch nhắc ----------

    def tick(self):
        """Đối chiếu toàn bộ lịch với hiện tại, rồi hẹn lần thức tiếp theo."""
        now = datetime.now()
        upcoming = None
        try:
            self._sync_hotkey()
            self._sync_listener(now)
            self._daily(now)
            late_limit = schedule.STARTUP_LATE_LIMIT if self.first_tick else schedule.LATE_LIMIT
            tasks = self.store.scheduled_tasks()
            sent = self.store.sent_keys()
            show, skip, upcoming = schedule.collect(tasks, sent, now, late_limit)
            block = schedule.active_block(tasks, now)
            pomo = self._pomodoro(now)
            self.pill.sync(self._pill_item(block, pomo))
            self._notify(show, now)
            self.store.mark_sent(show + skip)
            upcoming = _earliest(upcoming, self._telegram_reminders(tasks, sent, now), pomo and pomo.end)
            self.card.refresh(now)
            self._refresh_tray(now, block)
        except Exception as error:
            self.report(error)
        finally:
            self.first_tick = False
            self._arm_timer(now, upcoming)
            self.trim()

    def trim(self):
        if not (self.pill.item or self.card.queue or self.quick.hwnd):
            K32EmptyWorkingSet(GetCurrentProcess())  # sắp ngủ lâu: trả RAM vật lý cho hệ thống

    def _pomodoro(self, now):
        """Hết phiên Pomodoro thì chuyển phiên, rồi báo lần chuyển mới nhất, kể cả lần do giao diện chuyển khi agent chưa kịp.
        Trả về trạng thái nếu đồng hồ đang chạy."""
        if not self.store.setting("pomo_end") and self.store.setting("pomo_notice") == self.pomo_notice:
            return None  # không dùng Pomodoro thì không phải nạp module của nó
        from . import pomodoro
        pomodoro.complete_due(self.store, now)
        notice = self.store.setting("pomo_notice")
        if notice != self.pomo_notice:
            self.pomo_notice = notice
            _stamp, title, line = notice.split("|", 2)
            self._toast(title, [line])
        state = pomodoro.read(self.store)
        return state if state.end else None

    def _pill_item(self, block, pomo):
        """Đồng hồ nổi đếm khối giờ đang chạy, không có khối nào thì đếm phiên Pomodoro."""
        if block:
            task, start, end = block
            return PillItem("block", task["title"], start, end, task["block_start"], task["id"], False)
        if not pomo:
            return None
        from . import pomodoro
        task = self.store.get_task(pomo.task_id) if pomo.task_id and pomo.phase == pomodoro.FOCUS else None
        title = pomodoro.PHASE_NAMES[pomo.phase] + (f" · {task['title']}" if task else "")
        start = pomo.end - timedelta(minutes=pomodoro.minutes_of(pomodoro.config(self.store), pomo.phase))
        return PillItem("pomo", title, start, pomo.end, schedule.to_text_seconds(pomo.end), pomo.task_id, pomo.phase != pomodoro.FOCUS)

    def _telegram_reminders(self, tasks, sent, now):
        """Nhắc trước hạn qua Telegram. Gửi ở tiến trình riêng như bản tin; trả về mốc nhắc kế tiếp để hẹn giờ thức."""
        offsets = schedule.parse_offsets(self.store.setting("telegram_remind"))
        if not offsets or not self.store.setting("telegram_token") or not self.store.setting("telegram_chat_id"):
            return None
        send, skip, upcoming = schedule.telegram_reminders(tasks, offsets, sent, now)
        self.store.mark_sent(skip)
        if not send:
            return upcoming
        if not self.remind_spawned_at or now - self.remind_spawned_at >= REMIND_RETRY:
            self.remind_spawned_at = now
            ShellExecuteW(None, "open", pythonw(), f'"{RUN_SCRIPT}" --telegram-remind', ROOT, SW_HIDE)
        return _earliest(upcoming, now + REMIND_RETRY)  # quay lại xem tiến trình đã gửi được chưa

    def _summary_due(self, now):
        moment = self.store.setting("summary_time")
        return f"{now:%H:%M}" >= moment and self.store.setting("last_summary") != now.date().isoformat()

    def _daily(self, now):
        today = now.date().isoformat()
        if self.store.setting("last_maintenance") != today:
            self.store.maintenance(today)
            self.store.set_setting("last_maintenance", today)
        if self.pending_summary or (self._summary_due(now) and not self.locked):
            self.pending_summary = False
            self.send_summary(now)
        self._send_brief_if_due(now)

    def _send_brief_if_due(self, now):
        """Bản tin Telegram chạy ở tiến trình riêng: agent không nạp thư viện mạng, cũng không bị nghẽn."""
        settings = {key: self.store.setting(key) for key in schedule.BRIEF_SETTINGS}
        if self.first_tick or self.resumed:
            self.resumed = False
            self.brief_start_day = now.date()
        if not schedule.brief_due(settings, now, self.brief_start_day == now.date()):
            return
        if self.brief_spawned_at and now - self.brief_spawned_at < BRIEF_RETRY:
            return
        self.brief_spawned_at = now
        ShellExecuteW(None, "open", pythonw(), f'"{RUN_SCRIPT}" --telegram', ROOT, SW_HIDE)

    def send_summary(self, now):
        overdue, today = self.store.summary_tasks(now)
        title, lines = schedule.summary_message(overdue, today, now)
        self._toast(title, lines)
        self.store.set_setting("last_summary", now.date().isoformat())

    def _notify(self, events, now):
        if len(events) > MAX_INDIVIDUAL_ALERTS:
            self._toast(f"{len(events)} nhắc nhở cần xem", [task["title"] for task, _, _ in events[:3]])
            return
        available = user_is_available()
        for task, kind, _ in events:
            if available and kind != "block_start":
                self.card.push(task["id"], kind, now)
            else:
                self._toast(*self._toast_text(task, kind, now))

    @staticmethod
    def _toast_text(task, kind, now):
        title, line = schedule.describe_event(task, kind, now)
        return title, [line]

    def _toast(self, title, lines):
        try:
            toast.show(title, lines)
        except OSError as error:
            log(f"Toast WinRT lỗi ({error}), chuyển sang balloon")
            self._balloon(title, "\n".join(lines))

    def _refresh_tray(self, now, block):
        overdue, today = self.store.summary_tasks(now)
        tooltip = f"{APP_NAME}\n{len(today)} việc hôm nay · {len(overdue)} quá hạn"
        if block:
            tooltip += f"\nCòn {schedule.humanize(block[2] - now)}: {block[0]['title']}"
        self._update_tray(tooltip, ICON_ALERT_PATH if overdue else ICON_PATH)

    def _arm_timer(self, now, upcoming):
        midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
        targets = [now + MAX_SLEEP, midnight]
        if upcoming:
            targets.append(upcoming)
        for key in ("summary_time", "telegram_time"):
            hour, minute = self.store.setting(key).split(":")
            moment = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
            if moment > now:
                targets.append(moment)
        if self.pill.item or self.card.queue:
            targets.append(now + timedelta(minutes=1))  # cập nhật đếm ngược trên tooltip và thẻ nhắc
        delay = (min(targets) - now).total_seconds()
        SetTimer(self.hwnd, TIMER_TICK, max(int(delay * 1000) + 50, 200), None)

    # ---------- Thông điệp Windows ----------

    def _on_tray_event(self, wparam, lparam):
        event = low_word(lparam)
        if event in (NIN_SELECT, NIN_KEYSELECT, NIN_BALLOONUSERCLICK):
            self.open_ui()
        elif event == WM_CONTEXTMENU:
            self._show_menu(signed_word(wparam), signed_word(wparam >> 16))

    def _window_proc(self, hwnd, message, wparam, lparam):
        try:
            if message == WM_TIMER and wparam == TIMER_TICK:
                self.tick()
            elif message == WM_APP_TRIM:
                SetTimer(self.hwnd, TIMER_TRIM, TRIM_DELAY_MS, None)  # timer chỉ đặt được từ luồng sở hữu cửa sổ
            elif message == WM_TIMER and wparam == TIMER_TRIM:
                KillTimer(self.hwnd, TIMER_TRIM)
                self.trim()
            elif message == WM_APP_TRAY:
                self._on_tray_event(wparam, lparam)
            elif message == WM_APP_DATA or message == WM_TIMECHANGE:
                self.tick()
            elif message == WM_APP_OPEN:
                self.open_ui()
            elif message == WM_APP_SUMMARY:
                self.send_summary(datetime.now())
            elif message == WM_HOTKEY and wparam == HOTKEY_QUICK_ADD:
                self.quick.show()
            elif message == WM_POWERBROADCAST and wparam in (PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC):
                self.resumed = self.resumed or wparam == PBT_APMRESUMESUSPEND  # máy tự thức để bảo trì thì không tính
                self.tick()
            elif message == WM_WTSSESSION_CHANGE and wparam in (WTS_SESSION_LOCK, WTS_SESSION_UNLOCK):
                self.locked = wparam == WTS_SESSION_LOCK
                if not self.locked:
                    self.tick()
            elif message == self.taskbar_created:
                self._add_tray()  # Explorer khởi động lại: icon khay cũ đã mất
                self.tick()
            elif message in (WM_CLOSE, WM_ENDSESSION) and (message == WM_CLOSE or wparam):
                self.quit()
                return 0
            else:
                return DefWindowProcW(hwnd, message, wparam, lparam)
            return 0
        except Exception as error:
            self.report(error)
            return DefWindowProcW(hwnd, message, wparam, lparam)
