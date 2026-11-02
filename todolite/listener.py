"""Nghe tin nhắn gửi cho bot ngay trong agent, gần như không tốn gì khi chưa có tin.

Một luồng phụ nằm chờ trong WinHTTP theo kiểu long polling: Telegram giữ kết nối tới 50 giây và trả
lời ngay khi có tin, nên luồng ngủ trong hệ điều hành thay vì thức dậy dò hỏi. Luồng chỉ biết có tin.
Việc đọc tin và ghi việc là của tiến trình ngắn `run.pyw --telegram-inbox`, nhờ đó agent không phải
nạp json hay quickparse, còn lỗi khi xử lý một tin lạ cũng không đụng tới agent.
"""
import _thread
import time

from .bot import Bot
from .paths import ROOT, RUN_SCRIPT, log, pythonw
from .web import ApiError
from .win32 import WM_APP_DATA, post_agent, start_hidden, wait_process

RETRY_DELAY, MAX_RETRY_DELAY = 5, 60  # giây: máy vừa thức dậy, mạng thường chưa có ngay
FIX_DELAY = 1800  # token sai thì thử thưa đi, người dùng sửa trong Cài đặt là chạy lại ngay
MIN_POLL = 5  # máy chủ thật giữ kết nối lâu hơn thế này, trả lời sớm là proxy hay trang đăng nhập Wi-Fi
INBOX_TIMEOUT = 120


class Listener:
    def __init__(self, on_waiting):
        self.on_waiting = on_waiting  # gọi trước mỗi lượt chờ; agent hẹn trả RAM vật lý khi luồng đã nằm yên trong WinHTTP
        self.target = None  # (token, API URL) đang nghe, None là đang tạm dừng
        self.problem = ""
        self.started = False
        self.alarm = _thread.allocate_lock()
        self.alarm.acquire()

    def listen(self, target):
        """Đổi bot cần nghe. Lượt chờ đang dở của bot cũ tự kết thúc trong vòng một phút."""
        changed, self.target = target != self.target, target
        if target and not self.started:
            self.started = True
            _thread.start_new_thread(self._run, ())
        elif changed:
            self._ring()

    def _ring(self):
        try:
            self.alarm.release()
        except RuntimeError:
            pass  # chuông đang vang sẵn

    def _rest(self, seconds):
        self.alarm.acquire(timeout=seconds)

    def _report(self, problem):
        if problem != self.problem:
            self.problem = problem
            post_agent(WM_APP_DATA)

    def _read_inbox(self):
        """Đọc tin ở tiến trình riêng và chờ nó xong: hai lệnh getUpdates cùng lúc sẽ đá nhau."""
        process = start_hidden(pythonw(), f'"{pythonw()}" "{RUN_SCRIPT}" --telegram-inbox', ROOT)
        return bool(process) and wait_process(process, INBOX_TIMEOUT) == 0

    def _run(self):
        while True:
            try:
                self._listen()
            except Exception as error:  # luồng chết là mất tính năng tới lần mở app sau
                log(f"Luồng nghe Telegram lỗi: {type(error).__name__}")
                self._rest(MAX_RETRY_DELAY)

    def _listen(self):
        delay = RETRY_DELAY
        while True:
            target = self.target
            if target is None:
                self.alarm.acquire()
                continue
            started = time.monotonic()
            try:
                self.on_waiting()
                found = Bot(*target).wait_for_update()
            except ApiError as error:
                if error.permanent or (error.retry_after and delay > RETRY_DELAY):
                    self._report(str(error))  # xung đột thoáng qua khi bấm Lấy tự động thì chưa đáng báo
                self._rest(FIX_DELAY if error.permanent else max(delay, error.retry_after))
                delay = min(delay * 2, MAX_RETRY_DELAY)
                continue
            self._report("")
            if found and target == self.target and not self._read_inbox():
                self._rest(delay)
                delay = min(delay * 2, MAX_RETRY_DELAY)
                continue
            delay = RETRY_DELAY
            if not found and time.monotonic() - started < MIN_POLL:
                self._rest(RETRY_DELAY)
