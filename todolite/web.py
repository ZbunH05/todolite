"""Phần mạng dùng chung cho Telegram và AI, gọi thẳng WinHTTP có sẵn trong Windows.

Không dùng urllib hay ssl: hai thư viện đó kéo theo OpenSSL và hàng chục module Python. WinHTTP nằm
sẵn trong hệ thống, tự dùng proxy và kho chứng chỉ của Windows. Module này chỉ cần ctypes nên agent
nạp được để chờ tin nhắn; thư viện json chỉ được nạp lúc thật sự đọc phản hồi.
"""
import ctypes
from ctypes import byref, c_void_p, create_string_buffer
from ctypes import wintypes as w

NETWORK_ERRORS = (OSError, ValueError)
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
SAFE_PATH_CHARS = "-_.~:"

ACCESS_TYPE_AUTOMATIC_PROXY = 4
FLAG_SECURE = 0x00800000
QUERY_STATUS_CODE_NUMBER = 19 | 0x20000000
HEADERS_NUL_TERMINATED = 0xFFFFFFFF
ERROR_TIMEOUT = 12002


def _bind(name, restype, *argtypes):
    function = getattr(_winhttp, name)
    function.restype, function.argtypes = restype, argtypes
    return function


_winhttp = ctypes.WinDLL("winhttp", use_last_error=True)
WinHttpOpen = _bind("WinHttpOpen", c_void_p, w.LPCWSTR, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD)
WinHttpConnect = _bind("WinHttpConnect", c_void_p, c_void_p, w.LPCWSTR, w.WORD, w.DWORD)
WinHttpOpenRequest = _bind("WinHttpOpenRequest", c_void_p, c_void_p, w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, c_void_p, w.DWORD)
WinHttpSetTimeouts = _bind("WinHttpSetTimeouts", w.BOOL, c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)
WinHttpSendRequest = _bind("WinHttpSendRequest", w.BOOL, c_void_p, w.LPCWSTR, w.DWORD, c_void_p, w.DWORD, w.DWORD, ctypes.c_size_t)
WinHttpReceiveResponse = _bind("WinHttpReceiveResponse", w.BOOL, c_void_p, c_void_p)
WinHttpQueryHeaders = _bind("WinHttpQueryHeaders", w.BOOL, c_void_p, w.DWORD, w.LPCWSTR, c_void_p, w.LPDWORD, w.LPDWORD)
WinHttpQueryDataAvailable = _bind("WinHttpQueryDataAvailable", w.BOOL, c_void_p, w.LPDWORD)
WinHttpReadData = _bind("WinHttpReadData", w.BOOL, c_void_p, c_void_p, w.DWORD, w.LPDWORD)
WinHttpCloseHandle = _bind("WinHttpCloseHandle", w.BOOL, c_void_p)

_session = None  # dùng chung trong tiến trình: WinHTTP giữ kết nối TLS để lần gọi sau khỏi bắt tay lại


class ApiError(Exception):
    """permanent=True: lỗi cấu hình, thử lại không có ích. False: lỗi mạng, nên thử lại sau retry_after giây."""

    def __init__(self, message, permanent=False, retry_after=0):
        super().__init__(message)
        self.permanent = permanent
        self.retry_after = retry_after


def split_url(url):
    """(scheme, máy chủ, cổng, đường dẫn) của một URL, sai cú pháp thì báo ValueError."""
    scheme, _, rest = url.partition("://")
    scheme = scheme.lower()
    address, _, path = rest.partition("/")
    host, _, port = address.rpartition(":") if address.rfind(":") > address.rfind("]") else (address, "", "")
    number = int(port) if port else 443 if scheme == "https" else 80
    if not host.strip("[]") or host.startswith("[") != host.endswith("]") or any(char in host for char in "@?#\\ ") or not 0 < number < 65536:
        raise ValueError("URL không hợp lệ")
    return scheme, host.strip("[]").lower(), number, f"/{path}"


def check_api_url(url):
    """Chuẩn hoá API URL. Khoá đi kèm mọi yêu cầu nên bắt buộc https, trừ máy cục bộ dùng để thử nghiệm."""
    url = url.strip().rstrip("/")
    try:
        scheme, host, _, _ = split_url(url)
    except ValueError:
        scheme, host = "", ""
    if host and (scheme == "https" or (scheme == "http" and host in LOCAL_HOSTS)):
        return url
    raise ApiError("API URL phải bắt đầu bằng https://", permanent=True)


def quote(text):
    """Thoát ký tự lạ để chèn vào đường dẫn, phòng khi dán nhầm token có dấu cách hay chữ có dấu."""
    return "".join(char if char.isascii() and (char.isalnum() or char in SAFE_PATH_CHARS) else
                   "".join(f"%{byte:02X}" for byte in char.encode("utf-8")) for char in text)


def read_json(raw):
    """Phản hồi JSON dạng object. Trang lỗi HTML của proxy hay Wi-Fi công cộng thì trả về {}."""
    import json
    try:
        body = json.loads(raw)
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _failed():
    code = ctypes.get_last_error()
    return TimeoutError("Hết thời gian chờ") if code == ERROR_TIMEOUT else OSError(f"WinHTTP lỗi {code}")


def _check(result):
    if not result:
        raise _failed()
    return result


class Response:
    """Phản hồi đang mở, đọc dần được để câu trả lời AI hiện ra từng chữ. Dùng trong khối with."""

    def __init__(self, handles):
        self.handles = handles

    def __enter__(self):
        return self

    def __exit__(self, *_details):
        self.close()

    def close(self):
        while self.handles:
            WinHttpCloseHandle(self.handles.pop())

    @property
    def status(self):
        code, size = w.DWORD(), w.DWORD(ctypes.sizeof(w.DWORD))
        _check(WinHttpQueryHeaders(self.handles[-1], QUERY_STATUS_CODE_NUMBER, None, byref(code), byref(size), None))
        return code.value

    def read_some(self):
        """Phần dữ liệu đang có, chờ tới khi có ít nhất một byte. Hết phản hồi thì trả về b""."""
        available, received = w.DWORD(), w.DWORD()
        _check(WinHttpQueryDataAvailable(self.handles[-1], byref(available)))
        if not available.value:
            return b""
        buffer = create_string_buffer(available.value)
        _check(WinHttpReadData(self.handles[-1], buffer, available.value, byref(received)))
        return buffer.raw[:received.value]

    def read(self):
        return b"".join(iter(self.read_some, b""))

    def __iter__(self):
        """Từng dòng của phản hồi, không gồm ký tự xuống dòng."""
        rest = b""
        for chunk in iter(self.read_some, b""):
            *lines, rest = (rest + chunk).split(b"\n")
            yield from lines
        if rest:
            yield rest


def post(url, data, headers, timeout):
    """Gửi POST, trả về Response. Lỗi kết nối báo bằng OSError, hết giờ báo bằng TimeoutError."""
    global _session
    scheme, host, port, path = split_url(url)
    _session = _session or _check(WinHttpOpen("TodoLite", ACCESS_TYPE_AUTOMATIC_PROXY, None, None, 0))
    response = Response([])
    try:
        response.handles.append(_check(WinHttpConnect(_session, host, port, 0)))
        response.handles.append(_check(WinHttpOpenRequest(response.handles[0], "POST", path, None, None, None,
                                                          FLAG_SECURE if scheme == "https" else 0)))
        milliseconds = int(timeout * 1000)
        _check(WinHttpSetTimeouts(response.handles[-1], milliseconds, milliseconds, milliseconds, milliseconds))
        _check(WinHttpSendRequest(response.handles[-1], headers, HEADERS_NUL_TERMINATED, data, len(data), len(data), 0))
        _check(WinHttpReceiveResponse(response.handles[-1], None))
    except OSError:
        response.close()
        raise
    return response
