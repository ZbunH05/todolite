"""Cất bí mật (bot token, API key) bằng DPAPI của Windows.

Chỉ đúng tài khoản Windows này mới giải mã được, nên database hay bản sao lưu có lọt ra
ngoài cũng không lộ token. Không cần lưu khoá ở đâu cả, Windows tự quản lý.
"""
import binascii
import ctypes
from ctypes import POINTER, Structure, byref, c_char, c_void_p
from ctypes import wintypes as w

ENTROPY = b"TodoLite"
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _Blob(Structure):
    _fields_ = [("size", w.DWORD), ("data", POINTER(c_char))]


def _blob(raw):
    buffer = ctypes.create_string_buffer(raw, len(raw))
    return _Blob(len(raw), ctypes.cast(buffer, POINTER(c_char))), buffer


def _call(function, raw):
    source, _keep_source = _blob(raw)
    entropy, _keep_entropy = _blob(ENTROPY)
    result = _Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    native = getattr(crypt32, function)
    native.argtypes = [POINTER(_Blob), c_void_p, POINTER(_Blob), c_void_p, c_void_p, w.DWORD, POINTER(_Blob)]
    native.restype = w.BOOL
    if not native(byref(source), None, byref(entropy), None, None, CRYPTPROTECT_UI_FORBIDDEN, byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.LocalFree.argtypes = [c_void_p]
        kernel32.LocalFree.restype = c_void_p
        kernel32.LocalFree(ctypes.cast(result.data, c_void_p))


def protect(text):
    """Chuỗi -> chuỗi đã mã hoá, an toàn để lưu vào database."""
    return binascii.b2a_base64(_call("CryptProtectData", text.encode("utf-8")), newline=False).decode("ascii")


def unprotect(stored):
    """Giải mã. Trả về chuỗi rỗng nếu dữ liệu hỏng hoặc được mã hoá bởi tài khoản Windows khác."""
    try:
        return _call("CryptUnprotectData", binascii.a2b_base64(stored)).decode("utf-8")
    except (OSError, ValueError, binascii.Error):
        return ""
