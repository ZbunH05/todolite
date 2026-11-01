"""Dữ liệu lịch vạn niên: ngày lễ dương lịch, âm lịch và tục ngữ mỗi ngày."""
from datetime import date, timedelta

from .lunar import lunar_month_length, solar_to_lunar
from .schedule import days_in_month

SOLAR_EVENTS = {
    (1, 1): "Tết Dương lịch", (9, 1): "Ngày Học sinh, Sinh viên Việt Nam", (3, 2): "Ngày thành lập Đảng Cộng sản Việt Nam",
    (14, 2): "Lễ Tình nhân", (27, 2): "Ngày Thầy thuốc Việt Nam", (8, 3): "Ngày Quốc tế Phụ nữ",
    (26, 3): "Ngày thành lập Đoàn TNCS Hồ Chí Minh", (1, 4): "Ngày Cá tháng Tư", (30, 4): "Ngày Giải phóng miền Nam",
    (1, 5): "Ngày Quốc tế Lao động", (7, 5): "Ngày chiến thắng Điện Biên Phủ", (19, 5): "Ngày sinh Chủ tịch Hồ Chí Minh",
    (1, 6): "Ngày Quốc tế Thiếu nhi", (28, 6): "Ngày Gia đình Việt Nam", (11, 7): "Ngày Dân số Thế giới",
    (27, 7): "Ngày Thương binh Liệt sĩ", (19, 8): "Ngày Cách mạng Tháng Tám", (2, 9): "Ngày Quốc khánh",
    (10, 10): "Ngày Giải phóng Thủ đô", (20, 10): "Ngày Phụ nữ Việt Nam", (9, 11): "Ngày Pháp luật Việt Nam",
    (20, 11): "Ngày Nhà giáo Việt Nam", (1, 12): "Ngày Thế giới phòng chống AIDS",
    (22, 12): "Ngày thành lập Quân đội Nhân dân Việt Nam", (24, 12): "Lễ Giáng sinh",
}

LUNAR_EVENTS = {
    (1, 1): "Tết Nguyên Đán", (2, 1): "Mùng 2 Tết", (3, 1): "Mùng 3 Tết", (15, 1): "Tết Nguyên Tiêu (Rằm tháng Giêng)",
    (3, 3): "Tết Hàn thực", (10, 3): "Giỗ Tổ Hùng Vương", (15, 4): "Lễ Phật đản", (5, 5): "Tết Đoan ngọ",
    (15, 7): "Lễ Vu Lan", (15, 8): "Tết Trung thu", (9, 9): "Tết Trùng cửu", (10, 10): "Tết Thường tân",
    (15, 10): "Tết Hạ nguyên", (23, 12): "Tiễn Ông Công Ông Táo",
}

SAYINGS = (
    "Có công mài sắt, có ngày nên kim.", "Không thầy đố mày làm nên.", "Học thầy không tày học bạn.",
    "Đi một ngày đàng, học một sàng khôn.", "Uống nước nhớ nguồn.", "Ăn quả nhớ kẻ trồng cây.",
    "Tốt gỗ hơn tốt nước sơn.", "Một cây làm chẳng nên non, ba cây chụm lại nên hòn núi cao.",
    "Thất bại là mẹ thành công.", "Có chí thì nên.", "Lửa thử vàng, gian nan thử sức.",
    "Gần mực thì đen, gần đèn thì rạng.", "Một giọt máu đào hơn ao nước lã.", "Bán anh em xa, mua láng giềng gần.",
    "Ăn vóc học hay.", "Cần cù bù thông minh.", "Tích tiểu thành đại.", "Năng nhặt chặt bị.",
    "Kiến tha lâu cũng đầy tổ.", "Nước chảy đá mòn.", "Có kiêng có lành.", "Của bền tại người.",
    "Đói cho sạch, rách cho thơm.", "Giấy rách phải giữ lấy lề.", "Lời nói chẳng mất tiền mua, lựa lời mà nói cho vừa lòng nhau.",
    "Học ăn, học nói, học gói, học mở.", "Ở hiền gặp lành.", "Trăm hay không bằng tay quen.",
    "Một nghề cho chín còn hơn chín nghề.", "Chớ thấy sóng cả mà ngã tay chèo.", "Thua keo này, bày keo khác.",
    "Có đi có lại mới toại lòng nhau.", "Một miếng khi đói bằng một gói khi no.", "Lá lành đùm lá rách.",
    "Nhiễu điều phủ lấy giá gương, người trong một nước phải thương nhau cùng.", "Tiên học lễ, hậu học văn.",
    "Tay làm hàm nhai, tay quai miệng trễ.", "Việc hôm nay chớ để ngày mai.", "Đường đi khó không khó vì ngăn sông cách núi.",
    "Không có việc gì khó, chỉ sợ lòng không bền.",
)


def _nth_sunday(year, month, nth):
    first = date(year, month, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (nth - 1))


def events_on(day):
    """Tên các ngày lễ rơi vào một ngày dương."""
    names = []
    if (day.day, day.month) in SOLAR_EVENTS:
        names.append(SOLAR_EVENTS[(day.day, day.month)])
    if day == _nth_sunday(day.year, 5, 2):
        names.append("Ngày của Mẹ")
    if day == _nth_sunday(day.year, 6, 3):
        names.append("Ngày của Cha")
    lunar = solar_to_lunar(day)
    if not lunar.leap:
        if (lunar.day, lunar.month) in LUNAR_EVENTS:
            names.append(LUNAR_EVENTS[(lunar.day, lunar.month)])
        if lunar.month == 12 and lunar.day == lunar_month_length(day):
            names.append("Giao thừa")
    return names


def month_events(year, month):
    """[(ngày, tên lễ)] trong một tháng dương, theo thứ tự ngày."""
    events = []
    for number in range(1, days_in_month(year, month) + 1):
        day = date(year, month, number)
        events.extend((day, name) for name in events_on(day))
    return events


def daily_saying(day):
    return SAYINGS[day.toordinal() % len(SAYINGS)]
