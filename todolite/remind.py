"""Nhắc trước hạn qua Telegram, chạy trong tiến trình ngắn `run.pyw --telegram-remind`.

Agent tính lịch và mở tiến trình này khi có mốc tới lúc, như với bản tin mỗi ngày: agent không phải nạp
phần mạng, mạng chậm cũng không làm nghẽn nhắc việc trên máy. Tiến trình tính lại các mốc từ database,
gom thành một tin, gửi được rồi mới đánh dấu đã gửi; lỗi mạng thì để nguyên cho lượt thử sau của agent.
"""
import html
import time
from datetime import datetime

from .bot import Bot
from .db import Store
from .paths import log
from .schedule import from_text, humanize, parse_offsets, telegram_reminders, when_label
from .web import ApiError
from .win32 import acquire_mutex

MUTEX = "Local\\TodoLite.TelegramRemind"
ATTEMPTS, RETRY_DELAY, MAX_RETRY_DELAY = 3, 10, 60
MAX_ITEMS = 10
TITLE_LIMIT = 80


def _name(task):
    title = task["title"]
    return html.escape(title if len(title) <= TITLE_LIMIT else title[:TITLE_LIMIT - 1].rstrip() + "…", quote=False)


def _when(task, now):
    """'hôm nay 14:00', 'ngày mai 09:00', 'T6 09:30', '15/11 09:00'."""
    label = when_label(task["due_at"], 0, now)
    return label[0].lower() + label[1:] if label.startswith(("Hôm", "Ngày")) else label


def build(events, now):
    """Một tin cho mọi việc tới mốc nhắc cùng lúc, số thời gian còn lại tính theo lúc gửi."""
    tasks = sorted({task["id"]: task for task, _, _ in events}.values(), key=lambda task: (task["due_at"], task["id"]))
    if len(tasks) == 1:
        task = tasks[0]
        return f"<b>Tâu Bệ hạ, còn {humanize(from_text(task['due_at']) - now)} là tới hạn:</b>\n• <b>{_name(task)}</b>, hạn {_when(task, now)}"
    lines = [f"<b>Tâu Bệ hạ, có {len(tasks)} việc sắp tới hạn:</b>"]
    lines += [f"• <b>{_name(task)}</b>, hạn {_when(task, now)} (còn {humanize(from_text(task['due_at']) - now)})" for task in tasks[:MAX_ITEMS]]
    if len(tasks) > MAX_ITEMS:
        lines.append(f"• và {len(tasks) - MAX_ITEMS} việc khác")
    return "\n".join(lines)


def _give_up(store, now, message):
    store.set_setting("telegram_status", f"{now:%H:%M %d/%m}: {message}")
    log(f"Telegram: {message}")
    return False


def send_due(store, now=None, wait=time.sleep):
    """Gửi các nhắc đã tới lúc. Trả về True nếu đã gửi."""
    now = now or datetime.now()
    offsets = parse_offsets(store.setting("telegram_remind"))
    if not offsets:
        return False
    send, skip, _ = telegram_reminders(store.scheduled_tasks(), offsets, store.sent_keys(), now)
    store.mark_sent(skip)
    if not send:
        return False
    text = build(send, now)
    for attempt in range(1, ATTEMPTS + 1):
        try:
            Bot(store.secret("telegram_token"), store.setting("telegram_api_url")).send(store.setting("telegram_chat_id"), text)
        except ApiError as error:
            if error.permanent:
                store.mark_sent(send)  # lỗi cấu hình thì thử lại cũng vô ích; dòng trạng thái trong Cài đặt báo cho người dùng
                return _give_up(store, now, f"Không gửi được nhắc hạn. {error}")
            if attempt == ATTEMPTS:
                log(f"Telegram: chưa gửi được nhắc hạn, sẽ thử lại. {error}")
                return False
            wait(min(max(RETRY_DELAY, error.retry_after), MAX_RETRY_DELAY))
        else:
            store.mark_sent(send)
            return True


def main():
    """Điểm vào của tiến trình nhắc hạn: `run.pyw --telegram-remind`."""
    if acquire_mutex(MUTEX) is not None:
        send_due(Store(cache_kb=128))
