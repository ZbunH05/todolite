"""Phép tính của chuyển động: cuộn mượt, đường cong, nấc con lăn và bàn di chuột. Không nạp Tk nên kiểm thử được riêng."""
from math import ceil, exp

WHEEL_DELTA = 120  # một nấc con lăn, bàn di chuột cũng tính theo đơn vị này
WHEEL_PAGESCROLL = 0xFFFFFFFF  # Windows đặt "cuộn một trang mỗi nấc"
LINE_PIXELS = 36  # một dòng cuộn ở tỉ lệ 1, mặc định 3 dòng là 108 điểm ảnh mỗi nấc
WHEEL_TAU = 0.032  # giây; một nấc còn dưới nửa điểm ảnh sau chừng 170 ms
TOUCH_TAU = 0.010  # Windows đã tự gửi quán tính cho bàn di chuột, chỉ cần làm mượt rất nhẹ để theo sát ngón tay
SETTLE = 0.5  # còn cách đích chừng này thì đặt thẳng vào đích, dừng dứt khoát
GESTURE_GAP = 0.18  # giây không có nấc nào thì coi như lần vuốt đã xong
MIN_FRAME = 0.008  # khung hình không dày hơn 125 lần mỗi giây, màn hình nhanh hơn thì vẽ cách một nhịp


def clamp(value, low, high):
    return low if value < low else high if value > high else value


def split_touchpad(delta):
    """<TouchpadScroll> gói hai trục vào một số: 16 bit thấp là trục dọc, 16 bit cao là trục ngang, đều là số có dấu."""
    delta &= 0xFFFFFFFF
    vertical, horizontal = delta & 0xFFFF, delta >> 16
    return vertical - 0x10000 if vertical & 0x8000 else vertical, horizontal - 0x10000 if horizontal & 0x8000 else horizontal


def touchpad_delta(delta):
    """(trục dọc, có phải bàn di chuột) của một <TouchpadScroll>. Còn số dư của bàn di chuột thì Tk chuyển cả nấc tròn 120
    của con lăn thành sự kiện này, nấc tròn đó vẫn là con lăn và phải trượt như con lăn."""
    vertical = split_touchpad(delta)[0]
    return vertical, vertical % WHEEL_DELTA != 0


def notch_pixels(lines, viewport, scale):
    """Số điểm ảnh của một nấc theo cài đặt số dòng mỗi nấc của Windows. Đặt cuộn theo trang thì một nấc gần bằng một trang."""
    line = LINE_PIXELS * scale
    if lines == WHEEL_PAGESCROLL:
        return max(viewport - line, line)
    return lines * line


def ease_out(progress):
    """Bậc ba: nhanh lúc đầu, chậm dần về cuối, không nảy."""
    progress = clamp(progress, 0.0, 1.0)
    return 1 - (1 - progress) ** 3


def mix(start, end, progress):
    return start + (end - start) * progress


def approach(position, target, dt, tau):
    """Đi một phần quãng còn lại theo hàm mũ. Tính theo thời gian thật nên khung hình chậm chỉ đi được xa hơn, không làm chậm cả chuyển động."""
    if abs(target - position) <= SETTLE:
        return target
    return target - (target - position) * exp(-dt / tau)


def frame_period(refresh_hz):
    """Khoảng cách giữa hai khung hình, là bội số của nhịp màn hình để không khung nào lệch nhịp."""
    vsync = 1 / refresh_hz if refresh_hz and refresh_hz > 1 else 1 / 60
    return vsync * ceil(MIN_FRAME / vsync - 1e-9)


class Glide:
    """Vị trí cuộn đuổi theo một đích. Đích được chặn trong [0, limit] nên không bao giờ vượt quá hai đầu."""
    __slots__ = ("position", "target", "limit", "tau")

    def __init__(self):
        self.position = self.target = self.limit = 0.0
        self.tau = WHEEL_TAU

    def reset(self, position, limit):
        self.limit = max(limit, 0.0)
        self.position = self.target = clamp(position, 0.0, self.limit)

    def push(self, amount, tau=WHEEL_TAU):
        """Cộng thêm vào đích: các nấc liên tiếp dồn lại thay vì bắt đầu lại từ chỗ đang đứng."""
        self.aim(self.target + amount, tau)

    def aim(self, target, tau=WHEEL_TAU):
        self.target = clamp(target, 0.0, self.limit)
        self.tau = tau

    def finish(self):
        self.position = self.target

    def step(self, dt):
        """Đi một khung hình, trả về True nếu còn phải đi tiếp."""
        self.position = approach(self.position, self.target, dt, self.tau)
        return self.position != self.target


class Swipe:
    """Gom nấc nhỏ của bàn di chuột thành đúng một bước cho mỗi lần vuốt, kể cả phần quán tính Windows gửi thêm sau đó.

    Dùng cho những chỗ con lăn nhảy từng bước như lật tháng: không gom thì một lần vuốt hai ngón lật qua cả năm.
    """
    __slots__ = ("rest", "last", "spent", "gap")

    def __init__(self, gap=GESTURE_GAP):
        self.rest, self.last, self.spent, self.gap = 0, None, False, gap

    def feed(self, delta, now):
        """Trả về -1 (lùi), 1 (tới) hoặc 0. delta dương là cuộn lên, tức lùi."""
        if self.last is None or now - self.last > self.gap or (self.rest and (delta > 0) != (self.rest > 0)):
            self.rest, self.spent = 0, False  # lần vuốt mới, hoặc ngón tay đổi chiều
        self.last = now
        if self.spent:
            return 0
        self.rest += delta
        if abs(self.rest) < WHEEL_DELTA:
            return 0
        self.spent = True
        return -1 if self.rest > 0 else 1


class Steps:
    """Cộng dồn quãng cuộn tính theo dòng rồi trả về số dòng nguyên, phần lẻ để dành cho lần sau. Đổi chiều thì bỏ phần lẻ."""
    __slots__ = ("rest",)

    def __init__(self):
        self.rest = 0.0

    def feed(self, lines):
        if self.rest and (lines > 0) != (self.rest > 0):
            self.rest = 0.0
        self.rest += lines
        whole = int(self.rest)
        self.rest -= whole
        return whole


def thumb_box(offset, total, viewport, track, minimum):
    """(vị trí, độ dài) của con trượt trên rãnh dài track, None khi nội dung vừa khung."""
    if total <= viewport or track <= 0:
        return None
    length = min(max(track * viewport / total, minimum), track)
    return (track - length) * clamp(offset / (total - viewport), 0.0, 1.0), length


def thumb_offset(position, total, viewport, track, length):
    """Ngược lại với thumb_box: con trượt nằm ở position thì nội dung cuộn tới đâu."""
    room = track - length
    if room <= 0 or total <= viewport:
        return 0.0
    return clamp(position / room, 0.0, 1.0) * (total - viewport)
