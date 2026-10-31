"""Toast Windows thật qua WinRT, gọi trực tiếp bằng ctypes.

Không cần thư viện ngoài: mỗi toast mất khoảng 10-20 ms và chỉ tốn thêm chưa tới 1 MB RAM.
Toast ở đây chỉ để báo tin. Windows 11 mới chặn URI tuỳ chỉnh gọi từ toast bằng hộp thoại
chọn ứng dụng, nên việc cần bấm nút do ReminderCard (popups.py) đảm nhận.
"""
import ctypes
from ctypes import HRESULT, POINTER, WINFUNCTYPE, byref, c_uint32, c_ulong, c_void_p, c_wchar_p

from . import APP_ID
from .paths import ICON_PNG_PATH
from .win32 import GUID

_combase = ctypes.WinDLL("combase")
_HSTRING = c_void_p
_combase.WindowsCreateString.argtypes = [c_wchar_p, c_uint32, POINTER(_HSTRING)]
_combase.WindowsCreateString.restype = HRESULT
_combase.WindowsDeleteString.argtypes = [_HSTRING]
_combase.RoInitialize.argtypes = [c_uint32]
_combase.RoInitialize.restype = HRESULT
_combase.RoGetActivationFactory.argtypes = [_HSTRING, POINTER(GUID), POINTER(c_void_p)]
_combase.RoGetActivationFactory.restype = HRESULT
_combase.RoActivateInstance.argtypes = [_HSTRING, POINTER(c_void_p)]
_combase.RoActivateInstance.restype = HRESULT

_XML_DOCUMENT = "Windows.Data.Xml.Dom.XmlDocument"
_TOAST = "Windows.UI.Notifications.ToastNotification"
_MANAGER = "Windows.UI.Notifications.ToastNotificationManager"
_IID_XML_DOCUMENT = "F7F3A506-1E87-42D6-BCFB-B8C809FA5494"
_IID_XML_DOCUMENT_IO = "6CD0E74E-EE65-4489-9EBF-CA43E87BA637"
_IID_TOAST_FACTORY = "04124B20-82C6-4229-B109-FD9ED4662B53"
_IID_MANAGER_STATICS = "50AC103F-D235-4598-BBEF-98FE4D1A3AD4"

# Vị trí hàm trong vtable: IUnknown (0-2), IInspectable (3-5), rồi tới hàm của interface.
_SLOT_QUERY_INTERFACE, _SLOT_RELEASE = 0, 2
_SLOT_LOAD_XML = 6
_SLOT_CREATE_TOAST = 6
_SLOT_CREATE_NOTIFIER_WITH_ID = 7
_SLOT_SHOW = 6

_initialized = False


def _guid(text):
    digits = text.replace("-", "")
    return GUID(int(digits[:8], 16), int(digits[8:12], 16), int(digits[12:16], 16),
                (ctypes.c_ubyte * 8)(*bytes.fromhex(digits[16:])))


class _HString:
    def __init__(self, text):
        self.handle = _HSTRING()
        _combase.WindowsCreateString(text, len(text), byref(self.handle))

    def __enter__(self):
        return self.handle

    def __exit__(self, *_):
        _combase.WindowsDeleteString(self.handle)


def _method(instance, slot, *argtypes):
    vtable = ctypes.cast(instance, POINTER(POINTER(c_void_p))).contents
    function = WINFUNCTYPE(HRESULT, c_void_p, *argtypes)(vtable[slot])
    return lambda *args: function(instance, *args)


def _query(instance, iid):
    result = c_void_p()
    _method(instance, _SLOT_QUERY_INTERFACE, POINTER(GUID), POINTER(c_void_p))(byref(_guid(iid)), byref(result))
    return result


def _release(*instances):
    for instance in instances:
        if instance:
            vtable = ctypes.cast(instance, POINTER(POINTER(c_void_p))).contents
            WINFUNCTYPE(c_ulong, c_void_p)(vtable[_SLOT_RELEASE])(instance)


def _factory(class_name, iid):
    result = c_void_p()
    with _HString(class_name) as name:
        _combase.RoGetActivationFactory(name, byref(_guid(iid)), byref(result))
    return result


def _ensure_runtime():
    global _initialized
    if not _initialized:
        try:
            _combase.RoInitialize(0)
        except OSError:
            pass  # luồng đã khởi tạo COM ở chế độ khác: vẫn dùng được
        _initialized = True


def _show_xml(xml):
    _ensure_runtime()
    inspectable, document_io, document, toast_factory, toast, manager, notifier = (c_void_p() for _ in range(7))
    try:
        with _HString(_XML_DOCUMENT) as name:
            _combase.RoActivateInstance(name, byref(inspectable))
        document_io = _query(inspectable, _IID_XML_DOCUMENT_IO)
        with _HString(xml) as content:
            _method(document_io, _SLOT_LOAD_XML, _HSTRING)(content)
        document = _query(inspectable, _IID_XML_DOCUMENT)
        toast_factory = _factory(_TOAST, _IID_TOAST_FACTORY)
        _method(toast_factory, _SLOT_CREATE_TOAST, c_void_p, POINTER(c_void_p))(document, byref(toast))
        manager = _factory(_MANAGER, _IID_MANAGER_STATICS)
        with _HString(APP_ID) as app_id:
            _method(manager, _SLOT_CREATE_NOTIFIER_WITH_ID, _HSTRING, POINTER(c_void_p))(app_id, byref(notifier))
        _method(notifier, _SLOT_SHOW, c_void_p)(toast)
    finally:
        _release(notifier, manager, toast, toast_factory, document, document_io, inspectable)


def _escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _file_uri(path):
    """Đường dẫn -> file:///..., mã hoá dấu cách và ký tự tiếng Việt trong tên thư mục."""
    safe = "/:._-"
    encoded = "".join(char if char.isascii() and (char.isalnum() or char in safe) else
                      "".join(f"%{byte:02X}" for byte in char.encode("utf-8"))
                      for char in path.replace("\\", "/"))
    return f"file:///{encoded}"


def build_xml(title, lines):
    texts = "".join(f"<text>{_escape(text)}</text>" for text in (title, *lines))
    logo = f'<image placement="appLogoOverride" src="{_escape(_file_uri(ICON_PNG_PATH))}"/>'
    return f'<toast><visual><binding template="ToastGeneric">{texts}{logo}</binding></visual></toast>'


def show(title, lines):
    """Hiện toast, ném OSError nếu Windows từ chối (agent sẽ chuyển sang balloon)."""
    _show_xml(build_xml(title, lines))
