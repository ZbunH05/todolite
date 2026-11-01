"""Bot Telegram: bản tin công việc mỗi ngày, lời lẽ của một vị quan tâu lên hoàng thượng.

Module này không được agent nạp: thư viện mạng tốn thêm nhiều MB RAM, trong khi bản tin chỉ
gửi mỗi ngày một lần. Agent chạy `run.pyw --telegram` như một tiến trình riêng, sống vài giây
rồi thoát. Nhờ vậy agent vẫn nhẹ, còn lỗi mạng không bao giờ làm nghẽn vòng lặp của nó.
"""
import html
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from . import almanac, lunar
from .db import Store
from .paths import log
from .schedule import WEEKDAY_LONG, day_label, from_text, humanize
from .web import NETWORK_ERRORS, ApiError, check_api_url, read_json
from .win32 import acquire_mutex

DEFAULT_API_URL = "https://api.telegram.org"
REQUEST_TIMEOUT = 20
SEND_ATTEMPTS = 4
RETRY_DELAY = 15  # giây: lúc PC vừa bật, mạng thường chưa sẵn sàng ngay
MAX_RETRY_DELAY = 120
MESSAGE_LIMIT = 4096  # Telegram đếm theo đơn vị UTF-16, mỗi emoji chiếm 2
MAX_LIST_ITEMS = 8
MAX_TITLE_LENGTH = 80
UPCOMING_ITEMS = 3
SEND_MUTEX = "Local\\TodoLite.Telegram"
CLOSINGS = ("Thần kính chúc hoàng thượng vạn sự hanh thông.", "Thần xin hầu bên cạnh, nhắc hoàng thượng từng việc.",
            "Kính mong hoàng thượng long thể an khang.", "Thần xin kính chúc hoàng thượng một ngày thuận buồm xuôi gió.")


def _reason(code, description):
    """Lời giải thích dễ hiểu cho các lỗi thường gặp."""
    text = (description or "").lower()
    if code == 401:
        return "Bot Token không đúng hoặc đã bị thu hồi"
    if code == 404:
        return "Bot Token hoặc API URL không đúng"
    if code == 403:
        return "Bot bị chặn hoặc không có quyền nhắn vào chat này"
    if "chat not found" in text:
        return "Chat ID không đúng, hoặc bạn chưa nhắn /start cho bot"
    if code == 409:
        return "Bot đang dùng webhook hoặc chương trình khác nên không đọc được tin nhắn. Hãy nhập Chat ID bằng tay"
    return description or ("Máy chủ Telegram đang lỗi" if code >= 500 else "Không đọc được phản hồi của Telegram")


def _failure(status, body):
    code = body.get("error_code", status)
    retry_after = (body.get("parameters") or {}).get("retry_after", 0)
    return ApiError(_reason(code, body.get("description")), permanent=400 <= code < 500 and code != 429, retry_after=retry_after)


class Bot:
    def __init__(self, token, api_url=DEFAULT_API_URL):
        if not token:
            raise ApiError("Chưa nhập Bot Token", permanent=True)
        self.base = f"{check_api_url(api_url)}/bot{urllib.parse.quote(token, safe=':')}"

    def _call(self, method, payload=None):
        request = urllib.request.Request(f"{self.base}/{method}", data=json.dumps(payload or {}).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        try:
            try:
                with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                    status, raw = response.status, response.read()
            except urllib.error.HTTPError as error:
                with error:
                    status, raw = error.code, error.read()
        except NETWORK_ERRORS:
            # Không ghi nguyên văn lỗi: URL chứa token.
            raise ApiError("Không kết nối được tới Telegram") from None
        body = read_json(raw)
        if status == 200 and body.get("ok"):
            return body.get("result")
        raise _failure(status, body)

    def me(self):
        """Tên bot, dùng để kiểm tra token: '@ten_bot'."""
        return "@" + self._call("getMe")["username"]

    def send(self, chat_id, text):
        return self._call("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

    def latest_chat(self):
        """(id, tên) của cuộc trò chuyện vừa nhắn cho bot, hoặc None."""
        updates = self._call("getUpdates", {"limit": 100})
        for update in reversed(updates):
            message = update.get("message") or update.get("channel_post") or update.get("my_chat_member")
            if message and "chat" in message:
                chat = message["chat"]
                return str(chat["id"]), chat.get("title") or chat.get("first_name") or chat.get("username") or ""
        return None


def _mid_sentence(title):
    """Viết thường chữ đầu để đặt giữa câu, trừ từ viết tắt như 'API' và tên riêng như 'Hà Nội'."""
    words = title.split()
    if title[1:2].isupper() or (len(words) > 1 and words[1][0].isupper()):
        return title
    return title[0].lower() + title[1:]


def _name(task):
    title = task["title"]
    title = title if len(title) <= MAX_TITLE_LENGTH else title[:MAX_TITLE_LENGTH - 1].rstrip() + "…"
    return html.escape(_mid_sentence(title), quote=False)


def _moment(task):
    return "" if task["all_day"] else f" lúc {task['due_at'][11:16]}"


def _bullets(lines):
    shown = [f"• {line}" for line in lines[:MAX_LIST_ITEMS]]
    if len(lines) > MAX_LIST_ITEMS:
        shown.append(f"• và {len(lines) - MAX_LIST_ITEMS} việc khác")
    return shown


def _opening(now):
    today = now.date()
    converted = lunar.solar_to_lunar(today)
    spirit, good = lunar.day_spirit(today)
    lines = ["<b>Tâu hoàng thượng,</b>",
             f"Hôm nay là {WEEKDAY_LONG[today.weekday()]}, {today:%d/%m/%Y}, nhằm ngày {lunar.lunar_text(converted)} "
             f"năm {lunar.year_can_chi(converted.year)}.",
             f"Ngày {lunar.day_can_chi(today)}, {spirit} {'hoàng đạo' if good else 'hắc đạo'}."]
    events = almanac.events_on(today)
    if events:
        lines.append(f"Hôm nay là {', '.join(events)}.")
    return lines


def _today_section(tasks):
    if not tasks:
        return ["Hôm nay hoàng thượng không có deadline nào. Thiên hạ thái bình, xin hoàng thượng an tâm."]
    if len(tasks) == 1:
        return [f"Hôm nay hoàng thượng có deadline <b>{_name(tasks[0])}</b>{_moment(tasks[0])}."]
    lines = [f"Hôm nay hoàng thượng có {len(tasks)} deadline:"]
    lines.extend(_bullets([f"<b>{_name(task)}</b>{_moment(task)}" for task in tasks]))
    return lines


def _overdue_section(tasks, now):
    if not tasks:
        return []
    lines = [f"Thần xin nhắc, {len(tasks)} việc đã quá hạn còn chờ hoàng thượng định đoạt:"]
    lines.extend(_bullets([f"{_name(task)} (trễ {humanize(now - from_text(task['due_at']))})" for task in tasks]))
    return lines


def _blocks_section(rows):
    if not rows:
        return []
    entries = []
    for row in rows:
        start = from_text(row["block_start"])
        end = start + timedelta(minutes=row["block_minutes"])
        entries.append(f"{start:%H:%M}–{end:%H:%M} {_name(row)}")
    return ["Khối giờ đã định hôm nay:", *_bullets(entries)]


def _upcoming_section(tasks, now):
    lines = []
    for task in tasks[:UPCOMING_ITEMS]:
        day = from_text(task["due_at"]).date()
        left = (day - now.date()).days
        lines.append(f"• {day_label(day, now.date())}{_moment(task)}: {_name(task)}" + (f" (còn {left} ngày)" if left > 1 else ""))
    return ["Thần cũng xin tâu các việc sắp tới:", *lines] if lines else []


def _within_limit(text):
    """Chốt an toàn cho độ dài: mỗi dòng là HTML trọn vẹn nên bỏ bớt dòng cuối không làm hỏng thẻ."""
    lines = text.split("\n")
    while len("\n".join(lines).encode("utf-16-le")) // 2 > MESSAGE_LIMIT:
        lines.pop()
    return "\n".join(lines)


def build_brief(store, now):
    """Bản tin hôm nay dạng HTML của Telegram. Tên việc đã được thoát ký tự đặc biệt."""
    overdue, today = store.summary_tasks(now)
    sections = (_opening(now), _today_section(today), _overdue_section(overdue, now), _blocks_section(store.blocks_today(now)),
                _upcoming_section(store.list_tasks("upcoming", now), now), [CLOSINGS[now.date().toordinal() % len(CLOSINGS)]])
    return _within_limit("\n\n".join("\n".join(section) for section in sections if section))


def send_brief(store, now):
    Bot(store.secret("telegram_token"), store.setting("telegram_api_url")).send(store.setting("telegram_chat_id"), build_brief(store, now))


def _give_up(store, now, message):
    store.set_setting("telegram_status", f"{now:%H:%M %d/%m}: {message}")
    log(f"Telegram: {message}")
    return False


def send_scheduled(store=None, now=None, wait=time.sleep):
    """Gửi bản tin tự động, chạy trong tiến trình riêng. Trả về True nếu đã gửi."""
    store = store or Store(cache_kb=128)
    now = now or datetime.now()
    today = now.date().isoformat()
    if store.setting("telegram_last_sent") == today:
        return False  # tiến trình khác vừa gửi xong
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            send_brief(store, now)
        except ApiError as error:
            if error.permanent:
                store.set_setting("telegram_failed_on", today)  # lỗi cấu hình: mai mới thử lại
                return _give_up(store, now, f"Không gửi được. {error}")
            if attempt == SEND_ATTEMPTS:
                return _give_up(store, now, f"Chưa gửi được, sẽ thử lại. {error}")
            wait(min(max(RETRY_DELAY, error.retry_after), MAX_RETRY_DELAY))
        else:
            store.set_setting("telegram_last_sent", today)
            store.set_setting("telegram_status", f"{now:%H:%M %d/%m}: Đã gửi bản tin")
            return True


def main():
    """Điểm vào của tiến trình gửi: `run.pyw --telegram`."""
    mutex = acquire_mutex(SEND_MUTEX)
    if mutex is not None:
        send_scheduled()
