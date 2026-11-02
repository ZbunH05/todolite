"""Thêm việc và trả lời lệnh qua Telegram, chạy trong tiến trình ngắn `run.pyw --telegram-inbox`.

Agent chỉ biết có tin (xem listener.py) rồi mở tiến trình này để đọc hết tin, ghi việc, tâu lại và thoát.
Chỉ nhận tin từ đúng Chat ID trong Cài đặt: bot là công khai, ai cũng nhắn được, và người lạ không
nhận được phản hồi nào. Mỗi dòng là một việc, viết theo cú pháp của Thêm nhanh. Các lệnh /rp, /today,
/week trả lời bằng tờ tấu soạn ngay lúc đó (report.py).
"""
import html
from datetime import datetime

from .bot import Bot, ensure_commands
from .db import Store
from .paths import log
from .quickparse import describe, parse
from .web import ApiError
from .win32 import WM_APP_DATA, post_agent

MAX_LINES = 20
TITLE_LIMIT = 200  # tên quá dài thì cắt, nguyên văn được giữ trong ghi chú của việc
SHOWN_TITLE = 80
EXIT_FAILED = 1
REPORTS = {"/rp": "progress", "/today": "today", "/week": "week"}  # lệnh: hàm trong report.py

HELP = ("Muôn tâu Bệ hạ, thần xin ghi chép theo lời Bệ hạ.\n"
        "Bệ hạ cứ nhắn việc cần làm, mỗi dòng là một việc, viết như ô Thêm nhanh:\n"
        "<code>Nộp báo cáo mai 9h !1 #công-việc</code>\n"
        "<code>Tập gym t2 18h hằng tuần</code>\n"
        "Các lệnh của thần:\n"
        "/rp xem tình hình hôm nay tới lúc này\n"
        "/today xem hạn định hôm nay\n"
        "/week xem hạn định 7 ngày tới\n"
        "/huy xoá các việc vừa ghi nếu lỡ ghi nhầm")
UNKNOWN_COMMAND = "Tâu Bệ hạ, thần chưa rõ lệnh này."
NOT_TEXT = "Tâu Bệ hạ, thần chỉ đọc được chữ, xin Bệ hạ nhắn việc bằng văn bản."
NOTHING_TO_UNDO = "Tâu Bệ hạ, không còn việc nào vừa ghi để xoá."
BROKEN = "Tâu Bệ hạ, thần có lỗi, chưa ghi được tin vừa rồi. Xin Bệ hạ nhắn lại."
UNDO_HINT = "Lỡ ghi nhầm, Bệ hạ nhắn /huy."


def _clean(text):
    return html.escape(text, quote=False)


def _shown(title):
    return _clean(title if len(title) <= SHOWN_TITLE else title[:SHOWN_TITLE - 1].rstrip() + "…")


def _bullet(title, details):
    return f"• <b>{_shown(title)}</b>{f' ({_clean(details)})' if details else ''}"


def _command(text):
    """'/huy@ten_bot' -> '/huy'. Tin thường thì trả về chuỗi rỗng."""
    return text.split()[0].split("@")[0].lower() if text.startswith("/") else ""


def _seen(store, chat_id, message_id):
    """Mất mạng đúng lúc chưa kịp xác nhận thì Telegram gửi lại tin: mã tin trong một chat chỉ tăng, nên nhận ra được."""
    stored_chat, _, stored_id = store.setting("telegram_last_message").partition(":")
    return stored_chat == chat_id and message_id <= int(stored_id)


def _too_old(store, message):
    """Tin nhắn thử từ trước khi bật tính năng không được biến thành việc."""
    return message["date"] < int(store.setting("telegram_inbox_since") or 0)


def _add_line(store, line, sent_at, now):
    """Ghi một dòng thành việc. Trả về (mốc nhận diện để /huy, dòng tâu lại)."""
    fields = parse(line, sent_at)  # theo giờ gửi: PC tắt cả đêm thì chữ 'mai' vẫn đúng ngày người gửi nghĩ tới
    title = fields.pop("title")
    if len(title) > TITLE_LIMIT:
        fields["notes"] = title
        title = title[:TITLE_LIMIT - 1].rstrip() + "…"
    details = describe(fields, now, store.tag_label)
    task_id = store.add_task(title, **fields)
    return f"{task_id}@{store.get_task(task_id)['created_at']}", _bullet(title, details or "chưa có hạn")


def _add_lines(store, text, sent_at, now):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    added = [_add_line(store, line, sent_at, now) for line in lines[:MAX_LINES]]
    store.set_setting("telegram_last_added", ",".join(mark for mark, _ in added))
    head = f"Tâu Bệ hạ, thần đã ghi {len(added)} việc vào sổ:" if len(added) > 1 else "Tâu Bệ hạ, thần đã ghi vào sổ:"
    reply = [head, *(line for _, line in added)]
    if len(lines) > MAX_LINES:
        reply.append(f"Tin quá dài, thần chỉ ghi {MAX_LINES} dòng đầu, còn {len(lines) - MAX_LINES} dòng chưa ghi.")
    reply.append(UNDO_HINT)
    return len(added), "\n".join(reply)


def _undo(store):
    """Xoá các việc của tin gần nhất. So cả giờ tạo: id bị dùng lại sau khi xoá thì việc mới không bị vạ lây."""
    tasks = []
    for mark in filter(None, store.setting("telegram_last_added").split(",")):
        task_id, _, created_at = mark.partition("@")
        task = store.get_task(int(task_id))
        if task and task["created_at"] == created_at:
            tasks.append(task)
    if not tasks:
        return NOTHING_TO_UNDO
    for task in tasks:
        store.delete_task(task["id"])
    store.set_setting("telegram_last_added", "")
    return "\n".join(["Tâu Bệ hạ, thần đã xoá khỏi sổ:", *(_bullet(task["title"], "") for task in tasks)])


def _reply_to(store, message, now):
    """(số việc vừa ghi, lời tâu lại). Lời tâu là None nếu tin được bỏ qua."""
    text = (message.get("text") or message.get("caption") or "").strip()
    command = _command(text)
    if command in ("/start", "/help"):
        return 0, HELP
    if _too_old(store, message):
        return 0, None
    if command == "/huy":
        return 0, _undo(store)
    if command in REPORTS:
        from . import report
        return 0, getattr(report, REPORTS[command])(store, now)
    if command:
        return 0, f"{UNKNOWN_COMMAND}\n\n{HELP}"
    if not text:
        return 0, NOT_TEXT
    return _add_lines(store, text, datetime.fromtimestamp(message["date"]), now)


class Reader:
    def __init__(self, store, now):
        self.store, self.now = store, now
        self.chat_id = store.setting("telegram_chat_id")
        self.bot = None
        self.added = 0
        self.can_reply = True

    def _tell(self, text):
        """Mạng hỏng thì thôi không tâu nữa: việc đã ghi xong, chờ từng tin hết giờ chỉ giữ tiến trình lại lâu."""
        if text and self.can_reply:
            try:
                self.bot.send(self.chat_id, text)
            except ApiError:
                self.can_reply = False

    def handle(self, update):
        message = update.get("message")
        if not message or str(message["chat"]["id"]) != self.chat_id or _seen(self.store, self.chat_id, message["message_id"]):
            return
        try:
            added, reply = _reply_to(self.store, message, self.now)
        except Exception as error:  # một tin lạ không được chặn các tin sau nó
            log(f"Không xử lý được tin Telegram: {type(error).__name__}")
            added, reply = 0, BROKEN
        self.store.set_setting("telegram_last_message", f"{self.chat_id}:{message['message_id']}")
        self.added += added
        self._tell(reply)

    def read_all(self):
        self.bot = Bot(self.store.secret("telegram_token"), self.store.setting("telegram_api_url"))
        offset = None
        while True:
            updates = self.bot.updates(offset)
            if not updates:
                break
            for update in updates:
                self.handle(update)
            offset = updates[-1]["update_id"] + 1
        if self.can_reply:
            ensure_commands(self.store, self.bot)

    def report(self):
        if self.added:
            self.store.set_setting("telegram_status", f"{self.now:%H:%M %d/%m}: Đã ghi {self.added} việc từ tin nhắn")
            post_agent(WM_APP_DATA)


def read_messages(store, now=None):
    """Đọc hết tin đang chờ. Trả về True nếu đã đọc và xác nhận xong."""
    reader = Reader(store, now or datetime.now())
    try:
        reader.read_all()
    except ApiError as error:
        log(f"Telegram: chưa đọc được tin nhắn. {error}")
        return False
    finally:
        reader.report()
    return True


def main():
    """Điểm vào của tiến trình đọc tin: `run.pyw --telegram-inbox`."""
    if not read_messages(Store(cache_kb=128)):
        raise SystemExit(EXIT_FAILED)
