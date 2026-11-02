"""Gọi Bot API của Telegram. Tách khỏi telegram.py để agent chờ tin nhắn mà không phải nạp phần viết tờ tấu."""
from .web import NETWORK_ERRORS, ApiError, check_api_url, post, quote, read_json

DEFAULT_API_URL = "https://api.telegram.org"
JSON_HEADER = "Content-Type: application/json"
REQUEST_TIMEOUT = 20
LONG_POLL = 50  # giây, mức tối đa máy chủ Telegram cho phép
LONG_POLL_MARGIN = 10
LONG_POLL_REQUEST = b'{"timeout":%d,"limit":1,"allowed_updates":["message"]}' % LONG_POLL
UPDATE_MARK = b'"update_id"'
CONFLICT = 409
CONFLICT_NOTE = "Bot đang dùng webhook hoặc chương trình khác đang đọc tin của bot"
CONFLICT_RETRY = 30  # bấm Lấy tự động cũng gây xung đột, nhưng chỉ trong khoảnh khắc
UPDATES_PER_READ = 100
# Menu lệnh Telegram hiện khi gõ "/" trong khung chat. Đổi danh sách thì tăng COMMANDS_VERSION để bot đăng ký lại.
COMMANDS = (("rp", "Tình hình hôm nay tới lúc này"), ("today", "Hạn định hôm nay"), ("week", "Hạn định 7 ngày tới"),
            ("huy", "Xoá các việc vừa ghi"), ("help", "Cách nhắn việc cho bot"))
COMMANDS_VERSION = "2"


def ensure_commands(store, bot):
    """Đăng ký menu lệnh một lần sau mỗi lần danh sách đổi. Lỗi thì thôi, lần gửi sau thử lại: menu chỉ là tiện ích."""
    if store.setting("telegram_commands") == COMMANDS_VERSION:
        return
    try:
        bot.set_commands()
    except ApiError:
        return
    store.set_setting("telegram_commands", COMMANDS_VERSION)


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
    if code == CONFLICT:
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
        self.base = f"{check_api_url(api_url)}/bot{quote(token)}"

    def _post(self, method, data, timeout):
        try:
            with post(f"{self.base}/{method}", data, JSON_HEADER, timeout) as response:
                return response.status, response.read()
        except NETWORK_ERRORS:
            # Không ghi nguyên văn lỗi: URL chứa token.
            raise ApiError("Không kết nối được tới Telegram") from None

    def _call(self, method, payload=None):
        import json
        status, raw = self._post(method, json.dumps(payload or {}).encode("utf-8"), REQUEST_TIMEOUT)
        body = read_json(raw)
        if status == 200 and body.get("ok"):
            return body.get("result")
        raise _failure(status, body)

    def me(self):
        """Tên bot, dùng để kiểm tra token: '@ten_bot'."""
        return "@" + self._call("getMe")["username"]

    def send(self, chat_id, text):
        return self._call("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

    def set_commands(self):
        return self._call("setMyCommands", {"commands": [{"command": name, "description": text} for name, text in COMMANDS]})

    def latest_chat(self):
        """(id, tên) của cuộc trò chuyện vừa nhắn cho bot, hoặc None."""
        updates = self._call("getUpdates", {"limit": UPDATES_PER_READ, "allowed_updates": ["message", "channel_post", "my_chat_member"]})
        for update in reversed(updates):
            message = update.get("message") or update.get("channel_post") or update.get("my_chat_member")
            if message and "chat" in message:
                chat = message["chat"]
                return str(chat["id"]), chat.get("title") or chat.get("first_name") or chat.get("username") or ""
        return None

    def updates(self, offset=None):
        """Các tin chưa xác nhận. Gọi với offset lớn hơn update_id nào thì tin đó được xác nhận là đã đọc."""
        payload = {"limit": UPDATES_PER_READ, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload)

    def wait_for_update(self):
        """Giữ kết nối tới khi có tin hoặc hết LONG_POLL giây. Chỉ dò chuỗi, không phân tích JSON: agent không nạp json."""
        status, raw = self._post("getUpdates", LONG_POLL_REQUEST, LONG_POLL + LONG_POLL_MARGIN)
        if status == CONFLICT:
            raise ApiError(CONFLICT_NOTE, retry_after=CONFLICT_RETRY)
        if status != 200:
            raise _failure(status, {})
        return UPDATE_MARK in raw
