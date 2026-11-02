"""Âm lịch Việt Nam: đổi ngày, can chi, tiết khí, giờ và ngày hoàng đạo.

Tính bằng thiên văn theo múi giờ UTC+7 chứ không tra bảng, nên đúng cả những năm lịch Việt
Nam lệch lịch Trung Quốc. Quy tắc lập lịch theo công bố của Hồ Ngọc Đức, công thức điểm sóc
và kinh độ Mặt Trời theo Jean Meeus, Astronomical Algorithms (1998).
"""
import math
from collections import namedtuple
from datetime import date, timedelta
from functools import lru_cache

TIME_ZONE = 7
SYNODIC_MONTH = 29.530588853
NEW_MOON_EPOCH = 2415021.076998695  # điểm sóc số 0, ngày 1/1/1900
JULIAN_OFFSET = 1721425  # date.toordinal() + hằng số này = số ngày Julius

CAN = ("Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý")
CHI = ("Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi")
ZODIAC = ("Chuột", "Trâu", "Hổ", "Mèo", "Rồng", "Rắn", "Ngựa", "Dê", "Khỉ", "Gà", "Chó", "Lợn")
SOLAR_TERMS = ("Xuân phân", "Thanh minh", "Cốc vũ", "Lập hạ", "Tiểu mãn", "Mang chủng", "Hạ chí", "Tiểu thử",
               "Đại thử", "Lập thu", "Xử thử", "Bạch lộ", "Thu phân", "Hàn lộ", "Sương giáng", "Lập đông",
               "Tiểu tuyết", "Đại tuyết", "Đông chí", "Tiểu hàn", "Đại hàn", "Lập xuân", "Vũ thủy", "Kinh trập")
SPIRITS = ("Thanh Long", "Minh Đường", "Thiên Hình", "Chu Tước", "Kim Quỹ", "Kim Đường",
           "Bạch Hổ", "Ngọc Đường", "Thiên Lao", "Huyền Vũ", "Tư Mệnh", "Câu Trần")
GOOD_SPIRITS = frozenset((0, 1, 4, 5, 7, 10))  # lục hoàng đạo, các vị trí còn lại là hắc đạo

LunarDate = namedtuple("LunarDate", "day month year leap")
Hour = namedtuple("Hour", "name start end")


def julian_day(day):
    return day.toordinal() + JULIAN_OFFSET


def from_julian_day(number):
    return date.fromordinal(number - JULIAN_OFFSET)


def _new_moon(k):
    """Thời điểm điểm sóc thứ k tính từ 1/1/1900, theo ngày Julius."""
    t = k / 1236.85
    t2, t3 = t * t, t * t * t
    radian = math.pi / 180
    mean = 2415020.75933 + 29.53058868 * k + 0.0001178 * t2 - 0.000000155 * t3
    mean += 0.00033 * math.sin((166.56 + 132.87 * t - 0.009173 * t2) * radian)
    sun = (359.2242 + 29.10535608 * k - 0.0000333 * t2 - 0.00000347 * t3) * radian
    moon = (306.0253 + 385.81691806 * k + 0.0107306 * t2 + 0.00001236 * t3) * radian
    node = (21.2964 + 390.67050646 * k - 0.0016528 * t2 - 0.00000239 * t3) * radian
    correction = ((0.1734 - 0.000393 * t) * math.sin(sun) + 0.0021 * math.sin(2 * sun)
                  - 0.4068 * math.sin(moon) + 0.0161 * math.sin(2 * moon) - 0.0004 * math.sin(3 * moon)
                  + 0.0104 * math.sin(2 * node) - 0.0051 * math.sin(sun + moon) - 0.0074 * math.sin(sun - moon)
                  + 0.0004 * math.sin(2 * node + sun) - 0.0004 * math.sin(2 * node - sun)
                  - 0.0006 * math.sin(2 * node + moon) + 0.0010 * math.sin(2 * node - moon)
                  + 0.0005 * math.sin(2 * moon + sun))
    if t < -11:
        delta = 0.001 + 0.000839 * t + 0.0002261 * t2 - 0.00000845 * t3 - 0.000000081 * t * t3
    else:
        delta = -0.000278 + 0.000265 * t + 0.000262 * t2
    return mean + correction - delta


def _sun_longitude(moment):
    """Kinh độ Mặt Trời (độ, 0 đến 360) tại một thời điểm theo ngày Julius."""
    t = (moment - 2451545.0) / 36525
    t2 = t * t
    radian = math.pi / 180
    anomaly = (357.52910 + 35999.05030 * t - 0.0001559 * t2 - 0.00000048 * t * t2) * radian
    longitude = 280.46645 + 36000.76983 * t + 0.0003032 * t2
    longitude += (1.914600 - 0.004817 * t - 0.000014 * t2) * math.sin(anomaly)
    longitude += (0.019993 - 0.000101 * t) * math.sin(2 * anomaly) + 0.000290 * math.sin(3 * anomaly)
    return longitude % 360


@lru_cache(maxsize=4096)
def _new_moon_day(k):
    return math.floor(_new_moon(k) + 0.5 + TIME_ZONE / 24)


def _major_term(day_number):
    """Trung khí của một ngày (0 đến 11, mỗi cung 30 độ), xét lúc đầu ngày theo giờ địa phương."""
    return int(_sun_longitude(day_number - 0.5 - TIME_ZONE / 24) // 30)


@lru_cache(maxsize=512)
def _month_eleven(year):
    """Ngày bắt đầu tháng 11 âm: tháng chứa Đông chí, mốc để đếm các tháng trong năm."""
    k = math.floor((julian_day(date(year, 12, 31)) - 2415021) / SYNODIC_MONTH)
    start = _new_moon_day(k)
    return _new_moon_day(k - 1) if _major_term(start) >= 9 else start


@lru_cache(maxsize=512)
def _leap_offset(month_eleven):
    """Vị trí tháng nhuận: tháng đầu tiên sau tháng 11 không chứa trung khí nào."""
    k = math.floor((month_eleven - NEW_MOON_EPOCH) / SYNODIC_MONTH + 0.5)
    step = 1
    current = _major_term(_new_moon_day(k + step))
    while True:
        previous = current
        step += 1
        current = _major_term(_new_moon_day(k + step))
        if current == previous or step >= 14:
            return step - 1


def _month_start(number):
    """(ngày đầu tháng âm chứa ngày này, số thứ tự điểm sóc của tháng đó).

    Điểm sóc thực có lúc muộn hơn giá trị trung bình, nên phải lùi tới khi gặp đúng tháng:
    lùi đúng một bước như quy tắc thường thấy sẽ ra "mùng 0" vào những ngày như 07/05/2054.
    """
    k = math.floor((number - NEW_MOON_EPOCH) / SYNODIC_MONTH) + 1
    while _new_moon_day(k) > number:
        k -= 1
    return _new_moon_day(k), k


@lru_cache(maxsize=4096)
def solar_to_lunar(day):
    number = julian_day(day)
    month_start, _ = _month_start(number)
    first = _month_eleven(day.year)
    last = first
    if first >= month_start:
        lunar_year = day.year
        first = _month_eleven(day.year - 1)
    else:
        lunar_year = day.year + 1
        last = _month_eleven(day.year + 1)
    difference = (month_start - first) // 29
    lunar_month = difference + 11
    leap = False
    if last - first > 365:
        leap_position = _leap_offset(first)
        if difference >= leap_position:
            lunar_month = difference + 10
            leap = difference == leap_position
    if lunar_month > 12:
        lunar_month -= 12
    if lunar_month >= 11 and difference < 4:
        lunar_year -= 1
    return LunarDate(number - month_start + 1, lunar_month, lunar_year, leap)


def lunar_month_length(day):
    """Số ngày của tháng âm chứa ngày dương này: 29 là tháng thiếu, 30 là tháng đủ."""
    start, k = _month_start(julian_day(day))
    return _new_moon_day(k + 1) - start


def lunar_to_solar(lunar_day, lunar_month, lunar_year, leap=False):
    """Ngày dương của một ngày âm, hoặc None nếu ngày âm đó không tồn tại."""
    if not 1 <= lunar_month <= 12 or not 1 <= lunar_day <= 30:
        return None
    if lunar_month < 11:
        first, last = _month_eleven(lunar_year - 1), _month_eleven(lunar_year)
    else:
        first, last = _month_eleven(lunar_year), _month_eleven(lunar_year + 1)
    k = math.floor(0.5 + (first - NEW_MOON_EPOCH) / SYNODIC_MONTH)
    offset = (lunar_month - 11) % 12
    if last - first > 365:
        leap_position = _leap_offset(first)
        if leap and lunar_month != (leap_position - 2) % 12:
            return None
        if leap or offset >= leap_position:
            offset += 1
    elif leap:
        return None
    start = _new_moon_day(k + offset)
    if lunar_day > _new_moon_day(k + offset + 1) - start:
        return None
    return from_julian_day(start + lunar_day - 1)


def _day_chi(day):
    return (julian_day(day) + 1) % 12


def year_can_chi(year):
    return f"{CAN[(year + 6) % 10]} {CHI[(year + 8) % 12]}"


def year_chi(year):
    return CHI[(year + 8) % 12]


def year_zodiac(year):
    return ZODIAC[(year + 8) % 12]


def month_can_chi(month, year):
    return f"{CAN[(year * 12 + month + 3) % 10]} {CHI[(month + 1) % 12]}"


def day_can_chi(day):
    return f"{CAN[(julian_day(day) + 9) % 10]} {CHI[_day_chi(day)]}"


def first_hour_can_chi(day):
    """Can chi của giờ Tý đầu ngày."""
    return f"{CAN[(julian_day(day) - 1) * 2 % 10]} Tý"


def day_spirit(day):
    """(tên thần trực ngày, True nếu là ngày hoàng đạo). Thanh Long khởi theo tháng âm."""
    start = (solar_to_lunar(day).month - 1) % 6 * 2
    position = (_day_chi(day) - start) % 12
    return SPIRITS[position], position in GOOD_SPIRITS


def good_hours(day):
    """Sáu giờ hoàng đạo trong ngày. Thanh Long khởi theo địa chi của ngày."""
    start = (_day_chi(day) - 2) % 6 * 2
    return [Hour(CHI[index], (index * 2 + 23) % 24, (index * 2 + 1) % 24)
            for index in range(12) if (index - start) % 12 in GOOD_SPIRITS]


def term_index(day):
    """Vị trí tiết khí tại cuối ngày địa phương, nên ngày giao tiết mang tên tiết mới."""
    return int(_apparent_sun(julian_day(day) + 0.5 - TIME_ZONE / 24) // 15)


def _apparent_sun(moment):
    """Kinh độ biểu kiến: thêm hiệu chỉnh quang sai và chương động, lệch khoảng 8 phút thời gian."""
    t = (moment - 2451545.0) / 36525
    return (_sun_longitude(moment) - 0.00569 - 0.00478 * math.sin(math.radians(125.04 - 1934.136 * t))) % 360


def solar_term(day):
    return SOLAR_TERMS[term_index(day)]


def next_solar_term(day):
    """(tên tiết kế tiếp, ngày giao tiết)."""
    current = term_index(day)
    moment = day
    while term_index(moment) == current:
        moment += timedelta(days=1)
    return SOLAR_TERMS[term_index(moment)], moment


def lunar_label(day):
    """Chữ ngắn trong ô lịch: ngày đầu tháng ghi cả tháng, ví dụ '1/10'."""
    lunar = solar_to_lunar(day)
    return f"{lunar.day}/{lunar.month}" if lunar.day == 1 else str(lunar.day)


def lunar_text(lunar):
    """'21 tháng 9' hoặc '3 tháng 6 nhuận'."""
    return f"{lunar.day} tháng {lunar.month}{' nhuận' if lunar.leap else ''}"
