"""Phần mạng dùng chung cho Telegram và AI.

Agent không được nạp module này: thư viện mạng tốn hàng MB RAM. Giao diện cũng chỉ nạp khi
người dùng thật sự cần tới mạng.
"""
import json
import urllib.parse
from http.client import HTTPException

NETWORK_ERRORS = (OSError, ValueError, HTTPException)
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


class ApiError(Exception):
    """permanent=True: lỗi cấu hình, thử lại không có ích. False: lỗi mạng, nên thử lại sau retry_after giây."""

    def __init__(self, message, permanent=False, retry_after=0):
        super().__init__(message)
        self.permanent = permanent
        self.retry_after = retry_after


def check_api_url(url):
    """Chuẩn hoá API URL. Khoá đi kèm mọi yêu cầu nên bắt buộc https, trừ máy cục bộ dùng để thử nghiệm."""
    url = url.strip().rstrip("/")
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname
    except ValueError:
        host = None
    if host and (parts.scheme == "https" or (parts.scheme == "http" and host in LOCAL_HOSTS)):
        return url
    raise ApiError("API URL phải bắt đầu bằng https://", permanent=True)


def read_json(raw):
    """Phản hồi JSON dạng object. Trang lỗi HTML của proxy hay Wi-Fi công cộng thì trả về {}."""
    try:
        body = json.loads(raw)
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}
