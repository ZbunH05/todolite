"""Xem ngày: trực, nhị thập bát tú, sao tốt xấu, ngày kỵ, việc nên làm và nên kiêng.

Căn cứ: Phan Kế Bính, Việt Nam phong tục (1915), chương Xem ngày kén giờ; bảng sao theo tháng âm
của Tân Việt, Thiều Phong, Bàn về lịch vạn niên (1997), đúc kết từ Ngọc Hạp Thông Thư; nghĩa mười
hai trực và Bành Tổ bách kỵ theo Hiệp Kỷ Biện Phương Thư. Lời giải do app viết lại cho ngắn gọn.
Bảng sao đã đối chiếu từng ngày với các trang lịch Việt, xem tests/test_daybook.py.

Trực tính theo tháng tiết với giờ giao tiết thiên văn, các sao tính theo tháng âm, tháng nhuận
dùng chung bảng với tháng thường. Đây là dữ kiện văn hoá để tham khảo, không phải lời tiên đoán.
"""
import re
from collections import namedtuple
from datetime import timedelta
from functools import lru_cache

from . import lunar
from .lunar import CAN, CHI

WEDDING, OPENING, TRAVEL, GROUND, BUILD = "Cưới hỏi", "Khai trương", "Xuất hành", "Động thổ", "Xây sửa nhà"
MOVE, BURIAL, TOMB, MONEY, SIGN = "Nhập trạch", "An táng", "Sửa mộ", "Cầu tài, giao dịch", "Ký kết"
RITE, STUDY, POST, HEAL, LAWSUIT = "Cúng tế, cầu phúc", "Nhập học, thi cử", "Nhận chức", "Chữa bệnh", "Kiện tụng"
MEET, SEW, PLANT, DOOR, WATER = "Hội họp", "May mặc", "Gieo trồng", "Trổ cửa", "Khơi nước, đào giếng"
BED, BOAT, CLEAN, WRECK, STORE, MENDING = "Đóng giường", "Đi thuyền", "Dọn dẹp", "Phá dỡ", "Thu nợ, nhập kho", "Sửa chữa nhỏ"
TASK_ORDER = (WEDDING, OPENING, TRAVEL, MONEY, SIGN, GROUND, BUILD, MOVE, DOOR, WATER, BURIAL, TOMB, RITE, STUDY, POST, HEAL, MEET,
              LAWSUIT, PLANT, SEW, BED, BOAT, STORE, CLEAN, WRECK, MENDING)
MAJOR_WORKS = "Mọi việc lớn"

GOOD, AVERAGE, BAD = 1, 0, -1
GOOD_SCORE, BAD_SCORE = 2, -4
MAJOR, MINOR, SPECIFIC = 2, 1, 0  # đại kỵ, kỵ chung, chỉ kỵ vài việc
MARK_PENALTY = {MAJOR: 0, MINOR: 2, SPECIFIC: 1}  # ngày đại kỵ luôn là ngày xấu nên không cần trừ điểm

Truc = namedtuple("Truc", "name score note do avoid")
Mansion = namedtuple("Mansion", "name animal good do avoid")
Star = namedtuple("Star", "name good note tasks")
Mark = namedtuple("Mark", "name level note avoid")
Advice = namedtuple("Advice", "task reasons")
Slot = namedtuple("Slot", "name start end good spirit")
Travel = namedtuple("Travel", "name good note")
Clash = namedtuple("Clash", "work label reasons")
Reading = namedtuple("Reading", "quality title reason spirit spirit_good truc mansion good_stars bad_stars marks do avoid element "
                                "element_note clashes conflict harmony directions travel taboos")

TRUC = (
    Truc("Kiến", 1, "Khí khởi đầu, ngày tốt nhưng chưa nên động đến đất", (TRAVEL, MONEY, MEET), (GROUND, BUILD, BURIAL)),
    Truc("Trừ", 1, "Bỏ cũ đón mới, hợp việc dọn và trừ bỏ", (CLEAN, RITE, HEAL), (WEDDING, OPENING, SIGN)),
    Truc("Mãn", 1, "Đầy đủ, hợp lễ bái nhưng dễ tràn nên kiêng việc lớn", (RITE, SEW), (WEDDING, POST, BURIAL)),
    Truc("Bình", 1, "Phẳng lặng, nhiều việc dùng được", (MENDING, BUILD, MEET), (LAWSUIT,)),
    Truc("Định", 1, "Yên ổn, hợp việc cần gắn bó lâu dài", (WEDDING, SIGN, MEET, MOVE), (LAWSUIT, HEAL, TRAVEL)),
    Truc("Chấp", 1, "Nắm giữ, hợp việc tu tạo", (BUILD, PLANT, MENDING), (TRAVEL, MOVE, OPENING)),
    Truc("Phá", -6, "Nhật nguyệt tương xung, trăm việc khó thành, chỉ nên phá dỡ", (WRECK, HEAL), (WEDDING, OPENING, SIGN, GROUND, TRAVEL)),
    Truc("Nguy", -3, "Dễ gặp nguy, chỉ nên lễ bái cầu an", (RITE,), (WEDDING, OPENING, MOVE, BUILD, BOAT)),
    Truc("Thành", 2, "Việc dễ thành, chỉ kiêng tranh tụng", (OPENING, WEDDING, STUDY, POST, MOVE, BUILD), (LAWSUIT,)),
    Truc("Thu", 0, "Thu về, hợp việc gom góp, không hợp khởi sự", (STORE, MONEY, PLANT), (BURIAL, TRAVEL, OPENING)),
    Truc("Khai", 2, "Mở ra, hợp mọi việc khởi đầu", (OPENING, WEDDING, STUDY, BUILD, HEAL), (BURIAL, GROUND)),
    Truc("Bế", -1, "Đóng lại, không hợp khởi sự, chỉ nên đắp vá", (MENDING,), (OPENING, TRAVEL, HEAL)),
)

MANSIONS = (
    Mansion("Giác Mộc Giao", "giao long", True, (WEDDING, BUILD, STUDY), (BURIAL, TOMB)),
    Mansion("Cang Kim Long", "rồng", False, (SEW,), (BURIAL, WEDDING, LAWSUIT)),
    Mansion("Đê Thổ Lạc", "cừu", False, (), (BUILD, BURIAL, WEDDING, TRAVEL)),
    Mansion("Phòng Nhật Thố", "thỏ", True, (BUILD, BURIAL, WEDDING, TRAVEL, GROUND, SEW), ()),
    Mansion("Tâm Nguyệt Hồ", "chồn", False, (), (BUILD, WEDDING, BURIAL, LAWSUIT, BED)),
    Mansion("Vĩ Hỏa Hổ", "cọp", True, (BURIAL, WEDDING, BUILD, DOOR, WATER, OPENING, GROUND), (BED, BOAT)),
    Mansion("Cơ Thủy Báo", "beo", True, (BURIAL, TOMB, DOOR, OPENING, TRAVEL), (BED, BOAT)),
    Mansion("Đẩu Mộc Giải", "cua", True, (TOMB, DOOR, WATER, GROUND, SEW, MONEY, STUDY), (MOVE,)),
    Mansion("Ngưu Kim Ngưu", "trâu", False, (BOAT, SEW), (BUILD, WEDDING, DOOR, WATER, PLANT, OPENING, TRAVEL)),
    Mansion("Nữ Thổ Bức", "dơi", False, (SEW,), (DOOR, WATER, BURIAL, LAWSUIT)),
    Mansion("Hư Nhật Thử", "chuột", False, (), (BUILD, WEDDING, OPENING, DOOR, WATER)),
    Mansion("Nguy Nguyệt Yến", "chim én", False, (BURIAL, BED), (BUILD, DOOR, WATER, BOAT)),
    Mansion("Thất Hỏa Trư", "heo", True, (BUILD, WEDDING, BURIAL, DOOR, WATER, BOAT, GROUND), ()),
    Mansion("Bích Thủy Du", "nhím", True, (BUILD, WEDDING, BURIAL, DOOR, WATER, GROUND, OPENING, TRAVEL), ()),
    Mansion("Khuê Mộc Lang", "chó sói", False, (BUILD, STUDY), (BURIAL, OPENING, DOOR, WATER, LAWSUIT, BED)),
    Mansion("Lâu Kim Cẩu", "chó", True, (BUILD, WEDDING, DOOR, WATER, SEW), (BED, BOAT)),
    Mansion("Vị Thổ Trĩ", "chim trĩ", True, (BUILD, WEDDING, BURIAL, GROUND, PLANT), (BOAT,)),
    Mansion("Mão Nhật Kê", "gà", False, (BUILD,), (BURIAL, WEDDING, DOOR, WATER, OPENING, TRAVEL, BED)),
    Mansion("Tất Nguyệt Ô", "quạ", True, (BURIAL, WEDDING, DOOR, WATER, GROUND, PLANT, OPENING, TRAVEL), (BOAT,)),
    Mansion("Chủy Hỏa Hầu", "khỉ", False, (), (BURIAL, TOMB, BUILD)),
    Mansion("Sâm Thủy Viên", "vượn", True, (BUILD, DOOR, BOAT, WATER), (WEDDING, BURIAL, BED)),
    Mansion("Tỉnh Mộc Hãn", "rái cá", True, (BUILD, DOOR, WATER, POST, MOVE), (BURIAL, TOMB)),
    Mansion("Quỷ Kim Dương", "dê", False, (BURIAL, GROUND, SEW), (BUILD, WEDDING, DOOR, WATER)),
    Mansion("Liễu Thổ Chương", "hoẵng", False, (), (BURIAL, BUILD, DOOR, WATER)),
    Mansion("Tinh Nhật Mã", "ngựa", False, (BUILD,), (BURIAL, WEDDING, WATER)),
    Mansion("Trương Nguyệt Lộc", "nai", True, (BUILD, DOOR, WEDDING, BURIAL, PLANT, GROUND, WATER), (BOAT,)),
    Mansion("Dực Hỏa Xà", "rắn", False, (SEW,), (BURIAL, WEDDING, BUILD, DOOR, WATER)),
    Mansion("Chẩn Thủy Dẫn", "giun", True, (BUILD, BURIAL, WEDDING, TRAVEL, GROUND), (BOAT,)),
)
MANSION_OFFSET = 11  # số ngày Julius + 11 chia 28 dư 0 là sao Giác

# Mỗi sao: tên, lời giải, việc liên quan, ô theo tháng âm từ Giêng đến Chạp. Ô là can, chi, can_chi,
# nhiều lựa chọn cách nhau bằng dấu phẩy, dấu gạch ngang là tháng đó không có.
GOOD_STARS = (
    ("Thiên Đức", "Tốt mọi việc", (), "Đinh Thân Nhâm Tân Hợi Giáp Quý Dần Bính Ất Tỵ Canh"),
    ("Thiên Đức Hợp", "Tốt mọi việc", (), "Nhâm Tý Đinh Bính Dần Kỷ Mậu Hợi Tân Canh Thân Ất"),
    ("Nguyệt Đức", "Tốt mọi việc", (), "Bính Giáp Nhâm Canh Bính Giáp Nhâm Canh Bính Giáp Nhâm Canh"),
    ("Nguyệt Đức Hợp", "Tốt mọi việc, kỵ kiện tụng", (), "Tân Kỷ Đinh Ất Tân Kỷ Đinh Ất Tân Kỷ Đinh Ất"),
    ("Thiên Hỷ", "Tốt mọi việc, nhất là cưới hỏi", (WEDDING,), "Tuất Hợi Tý Sửu Dần Mão Thìn Tỵ Ngọ Mùi Thân Dậu"),
    ("Thiên Phú", "Tốt nhất cho làm nhà, khai trương, an táng", (BUILD, OPENING, BURIAL), "Thìn Tỵ Ngọ Mùi Thân Dậu Tuất Hợi Tý Sửu Dần Mão"),
    ("Thiên Quý", "Tốt mọi việc", (), "Giáp,Ất Giáp,Ất Giáp,Ất Bính,Đinh Bính,Đinh Bính,Đinh Canh,Tân Canh,Tân Canh,Tân Nhâm,Quý Nhâm,Quý Nhâm,Quý"),
    ("Thiên Xá", "Tốt cho lễ giải oan, kiêng động thổ", (RITE,), "Mậu_Dần Mậu_Dần Mậu_Dần Giáp_Ngọ Giáp_Ngọ Giáp_Ngọ Mậu_Thân Mậu_Thân Mậu_Thân Giáp_Tý Giáp_Tý Giáp_Tý"),
    ("Sinh Khí", "Tốt nhất cho làm nhà, động thổ, trồng cây", (BUILD, GROUND, PLANT), "Tý Sửu Dần Mão Thìn Tỵ Ngọ Mùi Thân Dậu Tuất Hợi"),
    ("Thiên Phúc", "Tốt mọi việc", (), "Kỷ Mậu - Tân,Quý Tân,Nhâm - Ất Giáp - Đinh Bính -"),
    ("Thiên Thành", "Tốt mọi việc", (), "Mùi Dậu Hợi Sửu Mão Tỵ Mùi Dậu Hợi Sửu Mão Tỵ"),
    ("Thiên Quan", "Tốt mọi việc", (), "Tuất Tý Dần Thìn Ngọ Thân Tuất Tý Dần Thìn Ngọ Thân"),
    ("Thiên Mã", "Tốt cho xuất hành, giao dịch, cầu tài", (TRAVEL, MONEY), "Ngọ Thân Tuất Tý Dần Thìn Ngọ Thân Tuất Tý Dần Thìn"),
    ("Thiên Tài", "Tốt cho cầu tài, khai trương", (MONEY, OPENING), "Thìn Ngọ Thân Tuất Tý Dần Thìn Ngọ Thân Tuất Tý Dần"),
    ("Địa Tài", "Tốt cho cầu tài, khai trương", (MONEY, OPENING), "Tỵ Mùi Dậu Hợi Sửu Mão Tỵ Mùi Dậu Hợi Sửu Mão"),
    ("Nguyệt Tài", "Tốt cho cầu tài, khai trương, xuất hành", (MONEY, OPENING, TRAVEL), "Ngọ Tỵ Tỵ Mùi Dậu Hợi Ngọ Tỵ Tỵ Mùi Dậu Hợi"),
    ("Nguyệt Ân", "Tốt mọi việc", (), "Bính Đinh Canh Kỷ Mậu Tân Nhâm Quý Canh Ất Giáp Tân"),
    ("Nguyệt Không", "Tốt cho làm nhà, đóng giường", (BUILD, BED), "Nhâm Canh Bính Giáp Nhâm Canh Bính Giáp Nhâm Canh Bính Giáp"),
    ("Minh Tinh", "Tốt mọi việc", (), "Thân Tuất Tý Dần Thìn Ngọ Thân Tuất Tý Dần Thìn Ngọ"),
    ("Thánh Tâm", "Tốt mọi việc, nhất là cầu phúc", (RITE,), "Hợi Tỵ Tý Ngọ Sửu Mùi Dần Thân Mão Dậu Thìn Tuất"),
    ("Ngũ Phú", "Tốt mọi việc", (), "Hợi Dần Tỵ Thân Hợi Dần Tỵ Thân Hợi Dần Tỵ Thân"),
    ("Lộc Khố", "Tốt cho cầu tài, khai trương, giao dịch", (MONEY, OPENING), "Thìn Tỵ Ngọ Mùi Thân Dậu Tuất Hợi Tý Sửu Dần Mão"),
    ("Phúc Sinh", "Tốt mọi việc", (), "Dậu Mão Tuất Thìn Hợi Tỵ Tý Ngọ Sửu Mùi Dần Thân"),
    ("Cát Khánh", "Tốt mọi việc", (), "Dậu Dần Hợi Thìn Sửu Ngọ Mão Thân Tỵ Tuất Mùi Tý"),
    ("Âm Đức", "Tốt mọi việc", (), "Dậu Mùi Tỵ Mão Sửu Hợi Dậu Mùi Tỵ Mão Sửu Hợi"),
    ("U Vi Tinh", "Tốt mọi việc", (), "Hợi Thìn Sửu Ngọ Mão Thân Tỵ Tuất Mùi Tý Dậu Dần"),
    ("Mãn Đức Tinh", "Tốt mọi việc", (), "Dần Mùi Thìn Dậu Ngọ Hợi Thân Sửu Tuất Mão Tý Tỵ"),
    ("Kính Tâm", "Tốt cho việc tang lễ", (BURIAL,), "Mùi Sửu Thân Dần Dậu Mão Tuất Thìn Hợi Tỵ Tý Ngọ"),
    ("Tuế Hợp", "Tốt mọi việc", (), "Sửu Tý Hợi Tuất Dậu Thân Mùi Ngọ Tỵ Thìn Mão Dần"),
    ("Nguyệt Giải", "Tốt mọi việc", (), "Thân Thân Dậu Dậu Tuất Tuất Hợi Hợi Ngọ Ngọ Mùi Mùi"),
    ("Quan Nhật", "Tốt mọi việc", (), "- Mão - - Ngọ - - Dậu - - Tý -"),
    ("Hoạt Điệu", "Tốt, nhưng gặp Thụ Tử thì xấu", (), "Tỵ Tuất Mùi Tý Dậu Dần Hợi Thìn Sửu Ngọ Mão Thân"),
    ("Giải Thần", "Tốt cho tế lễ, kiện tụng, giải được sao xấu", (RITE, LAWSUIT), "Thân Thân Tuất Tuất Tý Tý Dần Dần Thìn Thìn Ngọ Ngọ"),
    ("Phổ Hộ", "Tốt mọi việc, nhất là làm phúc, cưới hỏi, xuất hành", (WEDDING, TRAVEL), "Thân Dần Dậu Mão Tuất Thìn Hợi Tỵ Tý Ngọ Sửu Mùi"),
    ("Ích Hậu", "Tốt mọi việc, nhất là cưới hỏi", (WEDDING,), "Tý Ngọ Sửu Mùi Dần Thân Mão Dậu Thìn Tuất Tỵ Hợi"),
    ("Tục Thế", "Tốt mọi việc, nhất là cưới hỏi", (WEDDING,), "Sửu Mùi Dần Thân Mão Dậu Thìn Tuất Tỵ Hợi Ngọ Tý"),
    ("Yếu Yên", "Tốt mọi việc, nhất là cưới hỏi", (WEDDING,), "Dần Thân Mão Dậu Thìn Tuất Tỵ Hợi Ngọ Tý Mùi Sửu"),
    ("Dịch Mã", "Tốt mọi việc, nhất là xuất hành", (TRAVEL,), "Thân Tỵ Dần Hợi Thân Tỵ Dần Hợi Thân Tỵ Dần Hợi"),
    ("Tam Hợp", "Tốt mọi việc", (), "Ngọ,Tuất Mùi,Hợi Thân,Tý Dậu,Sửu Dần,Tuất Hợi,Mão Tý,Thìn Sửu,Tỵ Dần,Ngọ Mão,Mùi Thìn,Thân Tỵ,Dậu"),
    ("Lục Hợp", "Tốt mọi việc", (), "Hợi Tuất Dậu Thân Mùi Ngọ Tỵ Thìn Mão Dần Sửu Tý"),
    ("Mẫu Thương", "Tốt cho cầu tài, khai trương", (MONEY, OPENING), "Hợi,Tý Hợi,Tý Hợi,Tý Dần,Mão Dần,Mão Dần,Mão Thìn,Sửu Thìn,Sửu Thìn,Sửu Thân,Dậu Thân,Dậu Thân,Dậu"),
    ("Phúc Hậu", "Tốt cho cầu tài, khai trương", (MONEY, OPENING), "Dần Dần Dần Tỵ Tỵ Tỵ Thân Thân Thân Hợi Hợi Hợi"),
    ("Đại Hồng Sa", "Tốt mọi việc", (), "Tý,Sửu Tý,Sửu Tý,Sửu Thìn,Tỵ Thìn,Tỵ Thìn,Tỵ Ngọ,Mùi Ngọ,Mùi Ngọ,Mùi Thân,Tuất Thân,Tuất Thân,Tuất"),
    ("Dân Nhật", "Tốt mọi việc", (), "Ngọ Ngọ Ngọ Dậu Dậu Dậu Tý Tý Tý Mão Mão Mão"),
    ("Hoàng Ân", "Tốt mọi việc", (), "Tuất Sửu Dần Tỵ Dậu Mão Tý Ngọ Hợi Thìn Thân Mùi"),
)

BAD_STARS = (
    ("Thiên Cương", "Xấu mọi việc", (), "Tỵ Tý Mùi Dần Dậu Thìn Hợi Ngọ Sửu Thân Mão Tuất"),
    ("Hà Khôi", "Xấu mọi việc, nhất là khởi công xây nhà", (BUILD,), "Hợi Ngọ Sửu Thân Mão Tuất Tỵ Tý Mùi Dần Dậu Thìn"),
    ("Đại Hao", "Xấu mọi việc", (), "Ngọ Mùi Thân Dậu Tuất Hợi Tý Sửu Dần Mão Thìn Tỵ"),
    ("Tiểu Hao", "Xấu cho cầu tài, kinh doanh", (MONEY,), "Tỵ Ngọ Mùi Thân Dậu Tuất Hợi Tý Sửu Dần Mão Thìn"),
    ("Thiên Hoả", "Xấu cho lợp nhà", (BUILD,), "Tý Mão Ngọ Dậu Tý Mão Ngọ Dậu Tý Mão Ngọ Dậu"),
    ("Hoả Tai", "Xấu cho làm nhà, lợp nhà", (BUILD,), "Sửu Mùi Dần Thân Mão Dậu Thìn Tuất Tỵ Hợi Ngọ Tý"),
    ("Nguyệt Hoả", "Xấu cho lợp nhà, làm bếp", (BUILD,), "Tỵ Thìn Mão Dần Sửu Tý Hợi Tuất Dậu Thân Mùi Ngọ"),
    ("Thổ Phủ", "Kiêng xây dựng, động thổ", (BUILD, GROUND), "Dần Mão Thìn Tỵ Ngọ Mùi Thân Dậu Tuất Hợi Tý Sửu"),
    ("Thổ Ôn", "Kiêng xây dựng, đào ao giếng", (BUILD, WATER), "Thìn Tỵ Ngọ Mùi Thân Dậu Tuất Hợi Tý Sửu Dần Mão"),
    ("Thiên Ôn", "Kiêng xây dựng", (BUILD,), "Mùi Tuất Thìn Dần Ngọ Tý Dậu Thân Tỵ Hợi Tý Mão"),
    ("Thiên Tặc", "Xấu cho động thổ, nhập trạch, khai trương", (GROUND, MOVE, OPENING), "Thìn Dậu Dần Mùi Tý Tỵ Tuất Mão Thân Sửu Ngọ Hợi"),
    ("Địa Tặc", "Xấu cho an táng, động thổ, xuất hành", (BURIAL, GROUND, TRAVEL), "Sửu Tý Hợi Tuất Dậu Thân Mùi Ngọ Tỵ Thìn Mão Dần"),
    ("Hoang Vu", "Xấu mọi việc", (), "Tỵ,Dậu,Sửu Tỵ,Dậu,Sửu Tỵ,Dậu,Sửu Thân,Tý,Thìn Thân,Tý,Thìn Thân,Tý,Thìn Hợi,Mão,Mùi Hợi,Mão,Mùi Hợi,Mão,Mùi Dần,Ngọ,Tuất Dần,Ngọ,Tuất Dần,Ngọ,Tuất"),
    ("Băng Tiêu Ngoạ Hãm", "Xấu mọi việc", (), "Tỵ Tý Sửu Dần Mão Tuất Hợi Ngọ Mùi Thân Dậu Thìn"),
    ("Nguyệt Phá", "Xấu cho xây dựng nhà cửa", (BUILD,), "Thân Dậu Tuất Hợi Tý Sửu Dần Mão Thìn Tỵ Ngọ Mùi"),
    ("Lục Bất Thành", "Xấu cho xây dựng", (BUILD,), "Dần Ngọ Tuất Tỵ Dậu Sửu Thân Tý Thìn Hợi Mão Mùi"),
    ("Nhân Cách", "Xấu cho cưới hỏi, khởi tạo", (WEDDING,), "Dậu Mùi Tỵ Mão Sửu Hợi Dậu Mùi Tỵ Mão Sửu Hợi"),
    ("Thần Cách", "Kỵ cúng tế", (RITE,), "Tỵ Mão Sửu Hợi Dậu Mùi Tỵ Mão Sửu Hợi Dậu Mùi"),
    ("Phi Ma Sát", "Kỵ cưới hỏi, nhập trạch", (WEDDING, MOVE), "Tý Dậu Ngọ Mão Tý Dậu Ngọ Mão Tý Dậu Ngọ Mão"),
    ("Ngũ Quỹ", "Kỵ xuất hành", (TRAVEL,), "Ngọ Dần Thìn Dậu Mão Thân Sửu Tỵ Tý Hợi Mùi Tuất"),
    ("Nguyệt Kiến Chuyển Sát", "Kỵ động thổ", (GROUND,), "Mão Mão Mão Ngọ Ngọ Ngọ Dậu Dậu Dậu Tý Tý Tý"),
    ("Lỗ Ban Sát", "Kỵ khởi tạo", (BUILD,), "Tý Tý Tý Mão Mão Mão Ngọ Ngọ Ngọ Dậu Dậu Dậu"),
    ("Phủ Đầu Dát", "Kỵ khởi tạo", (BUILD,), "Thìn Thìn Thìn Mùi Mùi Mùi Dậu Dậu Dậu Tý Tý Tý"),
    ("Tam Tang", "Kỵ khởi tạo, cưới hỏi, an táng", (BUILD, WEDDING, BURIAL), "Thìn Thìn Thìn Mùi Mùi Mùi Tuất Tuất Tuất Sửu Sửu Sửu"),
    ("Ngũ Hư", "Kỵ khởi tạo, cưới hỏi, an táng", (BUILD, WEDDING, BURIAL), "Tỵ Dậu Sửu Thân Tý Thìn Hợi Mão Mùi Dần Ngọ Tuất"),
    ("Thổ Cẩm", "Kỵ xây dựng, an táng", (BUILD, BURIAL), "Hợi Hợi Hợi Dần Dần Dần Tỵ Tỵ Tỵ Thân Thân Thân"),
    ("Tứ Thời Cô Quả", "Kỵ cưới hỏi", (WEDDING,), "Sửu Sửu Sửu Thìn Thìn Thìn Mùi Mùi Mùi Tuất Tuất Tuất"),
    ("Cô Thần", "Kỵ cưới hỏi", (WEDDING,), "Tuất Hợi Tý Sửu Dần Mão Thìn Tỵ Ngọ Mùi Thân Dậu"),
    ("Quả Tú", "Kỵ cưới hỏi", (WEDDING,), "Thìn Tỵ Ngọ Mùi Thân Dậu Tuất Hợi Tý Sửu Dần Mão"),
    ("Không Phòng", "Kỵ cưới hỏi", (WEDDING,), "Thìn Tỵ Tý Tuất Hợi Mùi Dần Mão Ngọ Thân Dậu Sửu"),
    ("Nguyệt Yếm Đại Hoạ", "Xấu cho xuất hành, cưới hỏi", (TRAVEL, WEDDING), "Tuất Dậu Thân Mùi Ngọ Tỵ Thìn Mão Dần Sửu Tý Hợi"),
    ("Nguyệt Hư", "Xấu cho cưới hỏi, mở hàng", (WEDDING, OPENING), "Sửu Tuất Mùi Thìn Sửu Tuất Mùi Thìn Sửu Tuất Mùi Thìn"),
    ("Nguyệt Hình", "Xấu mọi việc", (), "Tỵ Tý Thìn Thân Ngọ Sửu Dần Dậu Mùi Hợi Mão Tuất"),
    ("Hoàng Sa", "Xấu cho xuất hành", (TRAVEL,), "Ngọ Dần Tý Ngọ Dần Tý Ngọ Dần Tý Ngọ Dần Tý"),
    ("Tiểu Hồng Sa", "Xấu mọi việc", (), "Tỵ Dậu Sửu Tỵ Dậu Sửu Tỵ Dậu Sửu Tỵ Dậu Sửu"),
    ("Lôi Công", "Xấu cho xây dựng nhà cửa", (BUILD,), "Dần Hợi Tỵ Thân Dần Hợi Tỵ Thân Dần Hợi Tỵ Thân"),
    ("Ly Sàng", "Kỵ cưới hỏi", (WEDDING,), "Dậu Dậu Dậu Dần,Ngọ Dần,Ngọ Dần,Ngọ Tuất Tuất Tuất Tỵ Tỵ Tỵ"),
    ("Quỷ Khốc", "Xấu cho cúng tế, an táng", (RITE, BURIAL), "Tuất Tuất Tuất Tuất Tuất Tuất Tuất Tuất Tuất Tuất Tuất Tuất"),
    ("Kiếp Sát", "Kỵ xuất hành, cưới hỏi, an táng, xây dựng", (TRAVEL, WEDDING, BURIAL, BUILD), "Hợi Thân Tỵ Dần Hợi Thân Tỵ Dần Hợi Thân Tỵ Dần"),
    ("Thiên Lại", "Xấu mọi việc", (), "Dậu Ngọ Mão Tý Dậu Ngọ Mão Tý Dậu Ngọ Mão Tý"),
    ("Thiên Ngục", "Xấu mọi việc", (), "Tý Mão Ngọ Dậu Tý Mão Ngọ Dậu Tý Mão Ngọ Dậu"),
    ("Tội Chỉ", "Xấu cho cúng tế, kiện tụng", (RITE, LAWSUIT), "Ngọ Tý Mùi Sửu Thân Dần Dậu Mão Tuất Thìn Hợi Tỵ"),
    ("Vãng Vong", "Kỵ xuất hành, cưới hỏi, cầu tài, động thổ", (TRAVEL, WEDDING, MONEY, GROUND), "Dần Tỵ Thân Hợi Mão Ngọ Dậu Tý Thìn Mùi Tuất Sửu"),
    ("Địa Phá", "Kiêng xây dựng", (BUILD,), "Hợi Tý Sửu Dần Mão Thìn Tỵ Ngọ Mùi Thân Dậu Tuất"),
    ("Cửu Không", "Kỵ xuất hành, cầu tài, khai trương", (TRAVEL, MONEY, OPENING), "Thìn Sửu Tuất Mùi Mão Tý Dậu Ngọ Dần Hợi Thân Tỵ"),
    ("Âm Thác", "Kỵ xuất hành, cưới hỏi, an táng", (TRAVEL, WEDDING, BURIAL), "Canh_Tuất Tân_Dậu Canh_Thân Đinh_Mùi Bính_Ngọ Đinh_Tỵ Giáp_Thìn Ất_Mão Giáp_Dần Quý_Sửu Nhâm_Tý Quý_Hợi"),
    ("Dương Thác", "Kỵ xuất hành, cưới hỏi, an táng", (TRAVEL, WEDDING, BURIAL), "Giáp_Dần Ất_Mão Giáp_Thìn Đinh_Tỵ Bính_Ngọ Đinh_Mùi Canh_Thân Tân_Dậu Canh_Tuất Quý_Hợi Nhâm_Tý Quý_Sửu"),
)

# Ngày kỵ tính theo chi hoặc can của tháng âm.
SAT_CHU = "Tỵ Tý Mùi Mão Thân Tuất Sửu Hợi Ngọ Dậu Dần Thìn".split()
SAT_CHU_YANG = "Tý Sửu Sửu Tuất Thìn Thìn Sửu Thìn Sửu Thìn Mùi Thìn".split()
THU_TU = "Tuất Thìn Hợi Tỵ Tý Ngọ Sửu Mùi Dần Thân Mão Dậu".split()
TRUNG_TANG = "Giáp Ất Kỷ Bính Đinh Kỷ Canh Tân Kỷ Nhâm Quý Kỷ".split()
TRUNG_PHUC = "Canh Tân Kỷ Nhâm Quý Mậu Giáp Ất Kỷ Nhâm Quý Kỷ".split()
TAM_NUONG = (3, 7, 13, 18, 22, 27)
NGUYET_KY = (5, 14, 23)
DUONG_CONG = {(1, 13), (2, 11), (3, 9), (4, 7), (5, 5), (6, 3), (7, 1), (7, 29), (8, 27), (9, 25), (10, 23), (11, 21), (12, 19)}
PHUC_DOAN = {"Tý": 10, "Sửu": 7, "Dần": 12, "Mão": 9, "Thìn": 6, "Tỵ": 3, "Ngọ": 0, "Mùi": 25, "Thân": 22, "Dậu": 19, "Tuất": 16, "Hợi": 13}
BEFORE_DIVIDE = ("Xuân phân", "Hạ chí", "Thu phân", "Đông chí")  # ngày trước các tiết này là Tứ Ly
BEFORE_START = ("Lập xuân", "Lập hạ", "Lập thu", "Lập đông")  # ngày trước các tiết này là Tứ Tuyệt

CAN_TABOOS = ("Không mở kho, tiền của dễ hao", "Không gieo trồng, ngàn gốc khó lên", "Không sửa bếp, dễ gặp hoả hoạn",
              "Không cắt tóc, đầu dễ sinh nhọt", "Không nhận đất đai, chủ không lành", "Không phá giao kèo, hai bên cùng thiệt",
              "Không dệt cửi, khung cửi dễ hỏng", "Không làm tương, chủ không được nếm", "Không tháo nước, khó phòng ngập",
              "Không kiện tụng, lý yếu địch mạnh")
CHI_TABOOS = ("Không xem bói, tự chuốc tai hoạ", "Không làm lễ đội mũ, chủ khó về quê", "Không cúng tế, thần linh không chứng",
              "Không đào giếng, nước không trong", "Không khóc lóc, dễ có trùng tang", "Không đi xa, tiền của hao hụt",
              "Không lợp nhà, chủ phải đổi dời", "Không uống thuốc lạ, độc khí vào ruột", "Không kê giường, ma quỷ vào phòng",
              "Không hội khách, dễ say sưa sinh chuyện", "Không ăn thịt chó, dễ sinh quái lạ", "Không cưới gả, bất lợi cho chú rể")

ELEMENTS = ("Hải Trung Kim", "Lư Trung Hoả", "Đại Lâm Mộc", "Lộ Bàng Thổ", "Kiếm Phong Kim", "Sơn Đầu Hoả", "Giản Hạ Thuỷ", "Thành Đầu Thổ",
            "Bạch Lạp Kim", "Dương Liễu Mộc", "Tuyền Trung Thuỷ", "Ốc Thượng Thổ", "Tích Lịch Hoả", "Tùng Bách Mộc", "Trường Lưu Thuỷ",
            "Sa Trung Kim", "Sơn Hạ Hoả", "Bình Địa Mộc", "Bích Thượng Thổ", "Kim Bạc Kim", "Phúc Đăng Hoả", "Thiên Hà Thuỷ", "Đại Dịch Thổ",
            "Thoa Xuyến Kim", "Tang Chá Mộc", "Đại Khê Thuỷ", "Sa Trung Thổ", "Thiên Thượng Hoả", "Thạch Lựu Mộc", "Đại Hải Thuỷ")
WUXING = ("Mộc", "Hoả", "Thổ", "Kim", "Thuỷ")  # hành sau được hành trước sinh, hành cách một bị khắc
CAN_WUXING = (0, 0, 1, 1, 2, 2, 3, 3, 4, 4)
CHI_WUXING = (4, 2, 0, 0, 2, 1, 1, 2, 3, 3, 2, 4)
DAY_KINDS = {0: ("Can chi đồng hành", "chuyên nhật", "tốt"), 1: ("Can sinh chi", "bảo nhật", "tốt"), 4: ("Chi sinh can", "nghĩa nhật", "tốt"),
             2: ("Can khắc chi", "chế nhật", "trung bình"), 3: ("Chi khắc can", "phạt nhật", "xấu")}

SIX_HARMONY = (1, 0, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2)
XI_DIRECTIONS = ("Đông Bắc", "Tây Bắc", "Tây Nam", "Chính Nam", "Đông Nam")
TAI_DIRECTIONS = ("Đông Nam", "Chính Đông", "Chính Nam", "Tây Nam", "Chính Tây")
# Hạc Thần đi hết tám hướng trong 44 ngày kể từ Kỷ Dậu, 16 ngày còn lại ở trên trời.
CRANE_ROUTE = ((6, "Đông Bắc"), (5, "Chính Đông"), (6, "Đông Nam"), (5, "Chính Nam"), (6, "Tây Nam"), (5, "Chính Tây"), (6, "Tây Bắc"), (5, "Chính Bắc"))
CRANE_START = 45

TRAVEL_DAYS = (
    (("Đường Phong", True, "Rất tốt, xuất hành thuận, cầu tài được như ý"),
     ("Kim Thổ", False, "Đi nhỡ tàu xe, cầu tài không được, dễ mất của"),
     ("Kim Dương", True, "Xuất hành tốt, có quý nhân phù trợ, tài lộc thông suốt"),
     ("Thuần Dương", True, "Xuất hành tốt, lúc về thuận lợi, nhiều cơ hội"),
     ("Đạo Tặc", False, "Rất xấu, xuất hành dễ bị hại, mất của"),
     ("Hảo Thương", True, "Xuất hành thuận, gặp người lớn vừa lòng, làm việc như ý")),
    (("Thiên Đạo", False, "Cầu tài nên tránh, được cũng tốn kém"),
     ("Thiên Môn", True, "Xuất hành làm mọi việc đều vừa ý, cầu được ước thấy"),
     ("Thiên Đường", True, "Xuất hành tốt, quý nhân phù trợ, buôn bán thuận lợi"),
     ("Thiên Tài", True, "Nên xuất hành, cầu tài thắng lợi, mọi việc thuận"),
     ("Thiên Tặc", False, "Xuất hành xấu, cầu tài không được, dễ mất cắp"),
     ("Thiên Dương", True, "Xuất hành tốt, cầu tài được, hỏi vợ được"),
     ("Thiên Hầu", False, "Xuất hành dễ cãi cọ, nên tránh"),
     ("Thiên Thương", True, "Xuất hành gặp cấp trên rất tốt, cầu tài được")),
    (("Chu Tước", False, "Xuất hành, cầu tài đều xấu, hay mất của, kiện cáo thua"),
     ("Bạch Hổ Đầu", True, "Xuất hành, cầu tài đều được, đi đâu cũng thông"),
     ("Bạch Hổ Kiếp", True, "Xuất hành, cầu tài được như ý, trăm sự thuận"),
     ("Bạch Hổ Túc", False, "Cấm đi xa, làm việc gì cũng không thành, rất xấu"),
     ("Huyền Vũ", False, "Xuất hành thường gặp cãi cọ, việc xấu, không nên đi"),
     ("Thanh Long Đầu", True, "Xuất hành nên đi sáng sớm, cầu tài thắng lợi"),
     ("Thanh Long Kiếp", True, "Xuất hành bốn phương đều tốt, trăm sự được như ý"),
     ("Thanh Long Túc", False, "Đi xa không nên, xuất hành xấu, tài lộc không có, kiện cáo đuối lý")),
)


# Cụm từ để nhận ra việc của người dùng thuộc loại nào trong sách lịch. Chỉ dùng cụm rõ nghĩa: thà bỏ sót còn hơn báo nhầm,
# nên không có những từ đơn như "khám" (khám phá), "kiện" (sự kiện), "ký" (đăng ký) hay "thi" (ôn thi).
WORK_PHRASES = (
    (WEDDING, ("đám cưới", "lễ cưới", "cưới vợ", "cưới chồng", "ăn hỏi", "đám hỏi", "dạm ngõ", "kết hôn")),
    (OPENING, ("khai trương", "mở cửa hàng", "mở quán")),
    (TRAVEL, ("xuất hành", "đi công tác", "du lịch", "đi xa", "chuyến bay", "về quê")),
    (SIGN, ("ký hợp đồng", "ký kết", "ký giấy")),
    (MONEY, ("giao dịch", "đầu tư", "mua nhà", "bán nhà", "mua xe", "bán xe", "mua đất", "bán đất")),
    (GROUND, ("động thổ", "khởi công", "đào móng")),
    (BUILD, ("xây nhà", "sửa nhà", "làm nhà", "lợp mái")),
    (MOVE, ("chuyển nhà", "nhập trạch", "về nhà mới")),
    (BURIAL, ("an táng", "chôn cất")),
    (TOMB, ("sửa mộ", "xây mộ")),
    (RITE, ("đi lễ", "đi chùa", "lễ chùa", "cúng")),
    (STUDY, ("nhập học", "đi thi", "kỳ thi", "thi cuối kỳ", "thi giữa kỳ", "thi học kỳ", "bảo vệ luận văn", "bảo vệ đồ án")),
    (POST, ("nhận chức", "nhận việc")),
    (HEAL, ("khám bệnh", "đi khám", "tái khám", "khám răng", "khám sức khoẻ", "khám sức khỏe", "nhổ răng", "phẫu thuật", "chữa bệnh")),
    (LAWSUIT, ("kiện tụng", "khởi kiện", "đi kiện", "ra toà", "ra tòa")),
    (PLANT, ("trồng cây", "gieo hạt")),
)
_WORK_PATTERNS = [(work, re.compile(r"(?<!\w)(?:" + "|".join(phrases) + r")(?!\w)")) for work, phrases in WORK_PHRASES]


def _build_stars(rows, good):
    return [(Star(name, good, note, tasks), tuple(frozenset(cell.split(",")) for cell in cells.split())) for name, note, tasks, cells in rows]


_STARS = _build_stars(GOOD_STARS, True) + _build_stars(BAD_STARS, False)


def _can_index(day):
    return (lunar.julian_day(day) + 9) % 10


def _chi_index(day):
    return (lunar.julian_day(day) + 1) % 12


def solar_month_chi(day):
    """Chi của tháng tiết: từ Lập xuân là tháng Dần, đổi tháng đúng ngày giao tiết."""
    return (lunar.term_index(day) - 21) % 24 // 2 + 2


def truc_of(day):
    return TRUC[(_chi_index(day) - solar_month_chi(day)) % 12]


def mansion_of(day):
    return MANSIONS[(lunar.julian_day(day) + MANSION_OFFSET) % 28]


def stars_of(day):
    """(sao tốt, sao xấu) của một ngày. Tháng nhuận dùng bảng của tháng chính."""
    month = lunar.solar_to_lunar(day).month - 1
    can, chi = CAN[_can_index(day)], CHI[_chi_index(day)]
    keys = {can, chi, f"{can}_{chi}"}
    hits = [star for star, cells in _STARS if cells[month] & keys]
    return [star for star in hits if star.good], [star for star in hits if not star.good]


def marks_of(day):
    """Các ngày kỵ mà ngày này phạm, việc nặng xếp trước."""
    converted = lunar.solar_to_lunar(day)
    month, number = converted.month - 1, converted.day
    can, chi = CAN[_can_index(day)], CHI[_chi_index(day)]
    marks = []
    if chi == THU_TU[month]:
        marks.append(Mark("Thụ Tử", MAJOR, "Trăm việc đều kỵ, không nên khởi sự", (MAJOR_WORKS,)))
    if (converted.month, number) in DUONG_CONG:
        marks.append(Mark("Dương Công Kỵ Nhật", MAJOR, "Trăm việc khó thành, rất xấu cho xây dựng, an táng", (MAJOR_WORKS, GROUND, BUILD, BURIAL)))
    if chi == SAT_CHU[month]:
        marks.append(Mark("Sát Chủ", MAJOR, "Một trong hai ngày kiêng nhất, xấu cho việc tang và sửa mộ", (MAJOR_WORKS, BURIAL, TOMB)))
    if chi == SAT_CHU_YANG[month]:
        marks.append(Mark("Sát Chủ Dương", SPECIFIC, "Kỵ xây dựng, cưới hỏi, buôn bán, nhận việc, đầu tư", (BUILD, WEDDING, MONEY, POST)))
    if truc_of(day).name == "Phá":
        marks.append(Mark("Nguyệt Phá", MINOR, "Trăng xung với tháng, trăm việc khó thành", (WEDDING, OPENING, GROUND, BUILD)))
    if number in TAM_NUONG:
        marks.append(Mark("Tam Nương", MINOR, "Kỵ việc trọng đại như cưới hỏi, khai trương, xuất hành", (WEDDING, OPENING, TRAVEL, GROUND, BUILD)))
    if number in NGUYET_KY:
        marks.append(Mark("Nguyệt Kỵ", MINOR, "Mùng năm, mười bốn, hai ba: đi chơi còn thiệt, nữa là đi buôn", (TRAVEL, MONEY)))
    if number == lunar.lunar_month_length(day):
        marks.append(Mark("Nguyệt Tận", MINOR, "Ngày cuối tháng âm, khí tháng đã hết, nên tránh khởi sự", (OPENING, WEDDING)))
    if can == TRUNG_TANG[month]:
        marks.append(Mark("Trùng Tang", SPECIFIC, "Kỵ an táng, cưới hỏi, xuất hành, xây nhà", (BURIAL, WEDDING, TRAVEL, BUILD)))
    if can == TRUNG_PHUC[month]:
        marks.append(Mark("Trùng Phục", SPECIFIC, "Kỵ an táng, cưới hỏi, xuất hành, xây nhà", (BURIAL, WEDDING, TRAVEL, BUILD)))
    if PHUC_DOAN[chi] == (lunar.julian_day(day) + MANSION_OFFSET) % 28:
        marks.append(Mark("Phục Đoạn", SPECIFIC, "Kỵ an táng, xuất hành, chia gia tài", (BURIAL, TRAVEL)))
    following = lunar.solar_term(day + timedelta(days=1))
    if following != lunar.solar_term(day):
        if following in BEFORE_DIVIDE:
            marks.append(Mark("Tứ Ly", MINOR, f"Ngày trước tiết {following}, khí âm dương rời nhau", (OPENING, TRAVEL)))
        elif following in BEFORE_START:
            marks.append(Mark("Tứ Tuyệt", MINOR, f"Ngày trước tiết {following}, khí mùa cũ đã dứt", (OPENING, TRAVEL)))
    return sorted(marks, key=lambda mark: -mark.level)


def hours_of(day):
    """Mười hai giờ trong ngày, từ giờ Tý. Thần trực giờ khởi theo chi của ngày."""
    start = (_chi_index(day) - 2) % 6 * 2
    return [Slot(CHI[index], (index * 2 + 23) % 24, (index * 2 + 1) % 24, (index - start) % 12 in lunar.GOOD_SPIRITS,
                 lunar.SPIRITS[(index - start) % 12]) for index in range(12)]


def travel_of(day):
    """Ngày xuất hành theo Khổng Minh: tháng âm chia ba nhóm, mỗi nhóm một vòng ngày."""
    converted = lunar.solar_to_lunar(day)
    cycle = TRAVEL_DAYS[(converted.month - 1) % 3]
    return Travel(*cycle[(converted.day - 1) % len(cycle)])


def directions_of(day):
    """Hướng Hỷ Thần, Tài Thần và Hạc Thần. Hạc Thần là None khi đang ở trên trời."""
    can = _can_index(day)
    position = (_sixty_index(day) - CRANE_START) % 60
    crane = None
    for days, direction in CRANE_ROUTE:
        if position < days:
            crane = direction
            break
        position -= days
    return XI_DIRECTIONS[can % 5], TAI_DIRECTIONS[can // 2], crane


def _sixty_index(day):
    """Vị trí của ngày trong lục thập hoa giáp, Giáp Tý là 0."""
    can, chi = _can_index(day), _chi_index(day)
    return (6 * can - 5 * chi) % 60


def element_of(day):
    return ELEMENTS[_sixty_index(day) // 2]


def _element_wuxing(index):
    return WUXING.index(ELEMENTS[index // 2].split()[-1])


def clashing_ages(day):
    """Hai tuổi kỵ ngày: cùng chi xung, một tuổi có can bị can ngày khắc, một tuổi có nạp âm bị nạp âm ngày khắc."""
    can, chi = _can_index(day), (_chi_index(day) + 6) % 12
    first = (can + 4) % 10
    ages = [first]
    own = _element_wuxing(_sixty_index(day))
    for other in range(can % 2, 10, 2):
        index = (6 * other - 5 * chi) % 60
        if other != first and (_element_wuxing(index) - own) % 5 == 2:
            ages.append(other)
    return [f"{CAN[item]} {CHI[chi]}" for item in ages]


def _triple(chi):
    return [CHI[(chi + 4) % 12], CHI[(chi + 8) % 12]]


def harmony_of(day):
    """(chi xung, chi lục hợp, hai chi tam hợp) của ngày."""
    chi = _chi_index(day)
    return CHI[(chi + 6) % 12], CHI[SIX_HARMONY[chi]], _triple(chi)


def taboos_of(day):
    """Hai điều kiêng trong Bành Tổ bách kỵ, theo can và chi của ngày."""
    return CAN_TABOOS[_can_index(day)], CHI_TABOOS[_chi_index(day)]


def day_kind(day):
    """Quan hệ ngũ hành giữa can và chi: (mô tả, tên ngày, mức tốt xấu)."""
    can, chi = CAN_WUXING[_can_index(day)], CHI_WUXING[_chi_index(day)]
    return DAY_KINDS[(chi - can) % 5]


def _merge(groups):
    """Gộp [(việc, căn cứ)] thành danh sách Advice theo thứ tự ưu tiên của TASK_ORDER."""
    found = {}
    for tasks, reason in groups:
        for task in tasks:
            found.setdefault(task, [])
            if reason not in found[task]:
                found[task].append(reason)
    order = {task: index for index, task in enumerate((MAJOR_WORKS, *TASK_ORDER))}
    return [Advice(task, found[task]) for task in sorted(found, key=order.__getitem__)]


def advice_of(truc, mansion, good_stars, bad_stars, marks):
    """Việc nên làm và nên kiêng. Việc vừa nên vừa kiêng thì kiêng, theo lẽ có kiêng có lành."""
    avoid = _merge([(mark.avoid, mark.name) for mark in marks] + [(truc.avoid, f"trực {truc.name}")]
                   + [(mansion.avoid, f"sao {mansion.name.split()[0]}")] + [(star.tasks, star.name) for star in bad_stars])
    if any(mark.level == MAJOR and MAJOR_WORKS in mark.avoid for mark in marks):
        return [], avoid  # ngày đại kỵ thì không khuyên khởi sự việc gì
    blocked = {item.task for item in avoid}
    if truc.name == "Phá":
        return _merge([(truc.do, f"trực {truc.name}")]), avoid  # trực Phá chỉ hợp việc phá dỡ, sao tốt không cứu được
    do = _merge([(truc.do, f"trực {truc.name}"), (mansion.do, f"sao {mansion.name.split()[0]}")] + [(star.tasks, star.name) for star in good_stars])
    return [item for item in do if item.task not in blocked], avoid


def _quality(spirit_good, truc, mansion, marks):
    score = (2 if spirit_good else -2) + truc.score + (1 if mansion.good else -1) - sum(MARK_PENALTY[mark.level] for mark in marks)
    if any(mark.level == MAJOR for mark in marks) or score <= BAD_SCORE:
        return BAD
    clean = not any(mark.level == MINOR for mark in marks)  # đã phạm ngày kỵ thì cùng lắm là trung bình
    return GOOD if score >= GOOD_SCORE and clean else AVERAGE


@lru_cache(maxsize=512)
def quality_of(day):
    """Đánh giá nhanh cho ô lịch: GOOD, AVERAGE hoặc BAD."""
    return _quality(lunar.day_spirit(day)[1], truc_of(day), mansion_of(day), marks_of(day))


def _reason(spirit, spirit_good, truc, mansion, marks):
    parts = [f"{'Hoàng đạo' if spirit_good else 'Hắc đạo'} {spirit}", f"trực {truc.name}", f"sao {mansion.name.split()[0]} {'tốt' if mansion.good else 'xấu'}"]
    if marks:
        parts.append("phạm " + ", ".join(mark.name for mark in marks))
    else:
        parts.append("không phạm ngày kỵ nào")
    return ", ".join(parts)


@lru_cache(maxsize=64)
def read_day(day):
    """Toàn bộ phần luận của một ngày."""
    spirit, spirit_good = lunar.day_spirit(day)
    truc, mansion = truc_of(day), mansion_of(day)
    good_stars, bad_stars = stars_of(day)
    marks = marks_of(day)
    do, avoid = advice_of(truc, mansion, good_stars, bad_stars, marks)
    quality = _quality(spirit_good, truc, mansion, marks)
    kind = day_kind(day)
    return Reading(quality, {GOOD: "Ngày tốt", AVERAGE: "Ngày trung bình", BAD: "Ngày xấu"}[quality], _reason(spirit, spirit_good, truc, mansion, marks),
                   spirit, spirit_good, truc, mansion, good_stars, bad_stars, marks, do, avoid, element_of(day),
                   f"{kind[0]}, {kind[1]} ({kind[2]})", clashing_ages(day), *_harmony_fields(day), directions_of(day), travel_of(day), taboos_of(day))


def _harmony_fields(day):
    conflict, six, three = harmony_of(day)
    return conflict, [six, *three]


def work_of(title):
    """Loại việc trong sách lịch mà tên việc của người dùng nhắc tới, hoặc None."""
    lowered = title.lower()
    return next((work for work, pattern in _WORK_PATTERNS if pattern.search(lowered)), None)


def clash_of(title, day):
    """Điều kiêng mà việc này vướng nếu làm vào ngày đó, hoặc None."""
    work = work_of(title)
    if work is None:
        return None
    avoid = {item.task: item for item in read_day(day).avoid}
    item = avoid.get(work) or avoid.get(MAJOR_WORKS)
    return Clash(work, item.task[0].lower() + item.task[1:], item.reasons) if item else None


def _is_clear(day, work):
    reading = read_day(day)
    return reading.quality != BAD and not {item.task for item in reading.avoid} & {work, MAJOR_WORKS}


def nearest_clear_day(day, work, today, span=14):
    """Ngày gần `day` nhất không kiêng việc này và không phải ngày xấu. Ưu tiên ngày trước, vì việc có hạn không nên dời lùi."""
    for gap in range(1, span + 1):
        for candidate in (day - timedelta(days=gap), day + timedelta(days=gap)):
            if candidate >= today and _is_clear(candidate, work):
                return candidate
    return None


def age_note(day, birth):
    """Lời nhắc riêng theo năm sinh âm lịch, hoặc None nếu ngày này không liên quan tới tuổi đó."""
    year = lunar.solar_to_lunar(birth).year
    name, chi = lunar.year_can_chi(year), lunar.year_chi(year)
    conflict, six, three = harmony_of(day)
    if name in clashing_ages(day):
        return False, f"Ngày này kỵ tuổi {name} của bạn"
    if chi == conflict:
        return False, f"Ngày này xung tuổi {chi} của bạn"
    if chi == six or chi in three:
        return True, f"Ngày này hợp tuổi {chi} của bạn"
    return None
