"""Phần xem ngày, đối chiếu với các trang lịch Việt và với lịch thiên văn."""
import json
import math
import os
import re
import unicodedata
import unittest
from collections import Counter
from datetime import date, timedelta

from todolite import almanac, daybook, lunar, sayings

REFERENCE = os.path.join(os.path.dirname(__file__), "data", "daybook_reference.json")
# Các trang lịch khớp nửa vời ba sao này: chỉ cần trùng can hoặc chi đã tính là phạm, sai với bảng gốc.
LOOSE_STARS = {"Thiên Xá", "Âm Thác", "Dương Thác"}


def star_names(day):
    good, bad = daybook.stars_of(day)
    return {star.name for star in good + bad}


class Truc(unittest.TestCase):
    def test_published_days(self):
        for day, name in ((date(2026, 11, 2), "Phá"), (date(2026, 11, 7), "Khai"), (date(2026, 11, 8), "Bế")):
            self.assertEqual(daybook.truc_of(day).name, name, day)

    def test_day_of_a_solar_term_repeats_the_truc_before_it(self):
        self.assertEqual(lunar.solar_term(date(2026, 11, 7)), "Lập đông")
        self.assertEqual(daybook.truc_of(date(2026, 11, 6)), daybook.truc_of(date(2026, 11, 7)))

    def test_month_follows_solar_terms_not_lunar_months(self):
        self.assertEqual(lunar.solar_to_lunar(date(2026, 11, 8)).month, 9)
        self.assertEqual(daybook.solar_month_chi(date(2026, 11, 8)), lunar.CHI.index("Hợi"))

    def test_every_truc_has_a_meaning(self):
        self.assertEqual(len(daybook.TRUC), 12)
        for truc in daybook.TRUC:
            self.assertTrue(truc.note and truc.do and truc.avoid, truc.name)


class Mansions(unittest.TestCase):
    def test_published_day(self):
        self.assertEqual(daybook.mansion_of(date(2026, 11, 2)).name, "Tất Nguyệt Ô")

    def test_each_mansion_keeps_its_weekday(self):
        day = date(2000, 1, 6)  # thứ Năm: Giác, Đẩu, Khuê, Tỉnh luân phiên
        for offset in range(0, 280, 7):
            self.assertEqual(daybook.MANSIONS.index(daybook.mansion_of(day + timedelta(days=offset))) % 7, 0)

    def test_cycle_of_twenty_eight(self):
        day = date(2026, 1, 1)
        self.assertEqual(len({daybook.mansion_of(day + timedelta(days=n)).name for n in range(28)}), 28)
        self.assertEqual(daybook.mansion_of(day), daybook.mansion_of(day + timedelta(days=28)))


class Stars(unittest.TestCase):
    def test_every_table_has_twelve_months(self):
        for _star, cells in daybook._STARS:
            self.assertEqual(len(cells), 12)
        tokens = {token for _star, cells in daybook._STARS for cell in cells for token in cell}
        for token in tokens - {"-"}:
            for part in token.split("_"):
                self.assertTrue(part in lunar.CAN or part in lunar.CHI, token)

    def test_star_names_are_unique(self):
        names = [star.name for star, _cells in daybook._STARS]
        self.assertEqual(len(names), len(set(names)))

    def test_reference_days(self):
        with open(REFERENCE, encoding="utf8") as source:
            reference = json.load(source)
        self.assertGreater(len(reference), 100)
        for key, names in reference.items():
            day = date.fromisoformat(key)
            with self.subTest(day=key):
                self.assertEqual(star_names(day) - LOOSE_STARS, set(names) - LOOSE_STARS)

    def test_leap_month_uses_the_table_of_its_month(self):
        leap = lunar.lunar_to_solar(5, 6, 2025, True)
        self.assertTrue(lunar.solar_to_lunar(leap).leap)
        chi = lunar.CHI[(lunar.julian_day(leap) + 1) % 12]
        self.assertEqual("Thiên Hỷ" in star_names(leap), chi == "Mão")


class Marks(unittest.TestCase):
    def names(self, day):
        return [mark.name for mark in daybook.marks_of(day)]

    def lunar_day(self, day, month, year=2026):
        return lunar.lunar_to_solar(day, month, year)

    def test_tam_nuong(self):
        for number in (3, 7, 13, 18, 22, 27):
            self.assertIn("Tam Nương", self.names(self.lunar_day(number, 4)))
        self.assertNotIn("Tam Nương", self.names(self.lunar_day(4, 4)))

    def test_nguyet_ky(self):
        for number in (5, 14, 23):
            self.assertIn("Nguyệt Kỵ", self.names(self.lunar_day(number, 4)))

    def test_nguyet_tan_is_the_last_day_of_the_lunar_month(self):
        self.assertIn("Nguyệt Tận", self.names(date(2026, 11, 8)))  # 30 tháng 9
        self.assertNotIn("Nguyệt Tận", self.names(date(2026, 11, 7)))

    def test_duong_cong(self):
        self.assertEqual(len(daybook.DUONG_CONG), 13)
        for month, number in daybook.DUONG_CONG:
            self.assertIn("Dương Công Kỵ Nhật", self.names(self.lunar_day(number, month)), (month, number))

    def test_most_feared_days_follow_the_month_table(self):
        month = 3
        for number in range(1, 30):
            day = self.lunar_day(number, month)
            chi = lunar.CHI[(lunar.julian_day(day) + 1) % 12]
            self.assertEqual("Thụ Tử" in self.names(day), chi == "Hợi")
            self.assertEqual("Sát Chủ" in self.names(day), chi == "Mùi")

    def test_day_before_a_season_turn(self):
        self.assertIn("Tứ Tuyệt", self.names(date(2026, 11, 6)))  # trước Lập đông
        self.assertIn("Tứ Ly", self.names(date(2026, 12, 21)))  # trước Đông chí

    def test_worst_marks_come_first(self):
        day = date(2026, 1, 1)
        for offset in range(400):
            levels = [mark.level for mark in daybook.marks_of(day + timedelta(days=offset))]
            self.assertEqual(levels, sorted(levels, reverse=True))


class Advice(unittest.TestCase):
    def test_avoid_wins_over_do(self):
        day = date(2026, 1, 1)
        for offset in range(800):
            reading = daybook.read_day(day + timedelta(days=offset))
            self.assertFalse({item.task for item in reading.do} & {item.task for item in reading.avoid}, day + timedelta(days=offset))

    def test_every_advice_names_its_reason(self):
        reading = daybook.read_day(date(2026, 11, 2))
        for item in reading.do + reading.avoid:
            self.assertTrue(item.reasons, item.task)

    def test_major_day_advises_nothing(self):
        day = next(date(2026, 1, 1) + timedelta(days=n) for n in range(60) if any(mark.name == "Thụ Tử" for mark in daybook.marks_of(date(2026, 1, 1) + timedelta(days=n))))
        reading = daybook.read_day(day)
        self.assertEqual(reading.do, [])
        self.assertEqual(reading.avoid[0].task, daybook.MAJOR_WORKS)
        self.assertEqual(reading.quality, daybook.BAD)

    def test_truc_pha_only_allows_its_own_work(self):
        reading = daybook.read_day(date(2026, 11, 2))
        self.assertEqual(reading.truc.name, "Phá")
        self.assertEqual({item.task for item in reading.do}, {daybook.WRECK, daybook.HEAL})
        self.assertEqual(reading.quality, daybook.BAD)
        self.assertIn("Nguyệt Phá", [mark.name for mark in reading.marks])

    def test_tasks_are_ordered(self):
        order = {task: index for index, task in enumerate((daybook.MAJOR_WORKS, *daybook.TASK_ORDER))}
        for item in daybook.GOOD_STARS + daybook.BAD_STARS:
            for task in item[2]:
                self.assertIn(task, order)
        reading = daybook.read_day(date(2026, 11, 13))
        self.assertEqual(reading.avoid, sorted(reading.avoid, key=lambda advice: order[advice.task]))

    def test_year_is_not_lopsided(self):
        counts = Counter(daybook.quality_of(date(2026, 1, 1) + timedelta(days=n)) for n in range(1096))
        for quality in (daybook.GOOD, daybook.AVERAGE, daybook.BAD):
            self.assertGreater(counts[quality], 150)
        self.assertLess(counts[daybook.BAD], 550)

    def test_reading_explains_itself(self):
        reading = daybook.read_day(date(2026, 11, 13))
        self.assertEqual(reading.title, "Ngày xấu")
        for part in ("Hắc đạo Huyền Vũ", "trực Định", "sao Cang xấu", "Nguyệt Kỵ"):
            self.assertIn(part, reading.reason)


class Works(unittest.TestCase):
    def test_recognises_clear_phrases(self):
        for title, work in (("Ký hợp đồng thuê nhà", daybook.SIGN), ("Lễ cưới anh Nam", daybook.WEDDING), ("Đi công tác Đà Nẵng", daybook.TRAVEL),
                            ("Khai trương quán", daybook.OPENING), ("Đi khám răng", daybook.HEAL), ("Chuyển nhà", daybook.MOVE)):
            self.assertEqual(daybook.work_of(title), work, title)

    def test_ignores_words_that_only_look_alike(self):
        for title in ("Dọn nhà", "Khám phá Hà Giang", "Sự kiện công ty", "Đăng ký môn học", "Ôn thi", "Gửi hợp đồng cho đối tác", "Viết báo cáo"):
            self.assertIsNone(daybook.work_of(title), title)

    def test_clash_uses_the_avoid_list_of_that_day(self):
        day = date(2026, 11, 2)  # trực Phá kiêng ký kết
        clash = daybook.clash_of("Ký hợp đồng", day)
        self.assertEqual((clash.work, clash.label), (daybook.SIGN, "ký kết"))
        self.assertIn("trực Phá", clash.reasons)

    def test_feared_day_blocks_every_recognised_work(self):
        clash = daybook.clash_of("Đi chùa", date(2026, 11, 18))  # phạm Thụ Tử
        self.assertEqual(clash.label, "mọi việc lớn")

    def test_no_clash_for_unknown_work(self):
        self.assertIsNone(daybook.clash_of("Viết báo cáo", date(2026, 11, 18)))

    def test_nearest_clear_day_prefers_going_earlier(self):
        today = date(2026, 11, 2)
        day = daybook.nearest_clear_day(date(2026, 11, 18), daybook.SIGN, today)
        self.assertLess(day, date(2026, 11, 18))
        self.assertEqual(daybook.read_day(day).quality in (daybook.GOOD, daybook.AVERAGE), True)
        self.assertNotIn(daybook.SIGN, {item.task for item in daybook.read_day(day).avoid})

    def test_nearest_clear_day_never_returns_the_past(self):
        today = date(2026, 11, 18)
        self.assertGreater(daybook.nearest_clear_day(today, daybook.SIGN, today), today)


class Ages(unittest.TestCase):
    PUBLISHED = {"Giáp Tý": {"Mậu Ngọ", "Nhâm Ngọ"}, "Bính Dần": {"Canh Thân", "Nhâm Thân"}, "Canh Thìn": {"Giáp Tuất", "Mậu Tuất"},
                 "Ất Dậu": {"Kỷ Mão", "Đinh Mão"}, "Bính Tuất": {"Canh Thìn", "Nhâm Thìn"}}

    def test_published_clashes(self):
        day = date(2026, 1, 1)
        seen = 0
        for offset in range(60):
            current = day + timedelta(days=offset)
            name = lunar.day_can_chi(current)
            if name in self.PUBLISHED:
                seen += 1
                self.assertEqual(set(daybook.clashing_ages(current)), self.PUBLISHED[name], name)
        self.assertEqual(seen, len(self.PUBLISHED))

    def test_harmony_of_thin(self):
        day = date(2026, 11, 2)  # ngày Canh Thìn
        conflict, six, three = daybook.harmony_of(day)
        self.assertEqual((conflict, six, set(three)), ("Tuất", "Dậu", {"Tý", "Thân"}))

    def test_personal_note(self):
        day = date(2026, 11, 2)
        self.assertEqual(daybook.age_note(day, date(1958, 6, 1)), (False, "Ngày này kỵ tuổi Mậu Tuất của bạn"))
        self.assertEqual(daybook.age_note(day, date(1982, 6, 1)), (False, "Ngày này xung tuổi Tuất của bạn"))
        self.assertEqual(daybook.age_note(day, date(1993, 6, 1)), (True, "Ngày này hợp tuổi Dậu của bạn"))
        self.assertIsNone(daybook.age_note(day, date(1990, 6, 1)))


class Directions(unittest.TestCase):
    def test_published_day(self):
        self.assertEqual(daybook.directions_of(date(2026, 11, 2)), ("Tây Bắc", "Tây Nam", "Chính Tây"))

    def test_crane_rests_sixteen_days(self):
        day = date(2026, 1, 1)
        rests = sum(daybook.directions_of(day + timedelta(days=n))[2] is None for n in range(60))
        self.assertEqual(rests, 16)

    def test_travel_days(self):
        self.assertEqual(daybook.travel_of(date(2026, 11, 2)).name, "Thanh Long Túc")
        self.assertFalse(daybook.travel_of(date(2026, 11, 2)).good)


class HiddenDetails(unittest.TestCase):
    def test_element_table(self):
        self.assertEqual(daybook.element_of(date(2026, 11, 2)), "Bạch Lạp Kim")
        self.assertEqual(len(daybook.ELEMENTS), 30)

    def test_day_kind(self):
        self.assertEqual(daybook.day_kind(date(2026, 11, 2))[1], "nghĩa nhật")  # Thổ sinh Kim
        self.assertEqual(daybook.day_kind(date(2026, 11, 7))[1], "phạt nhật")  # Kim khắc Mộc

    def test_twelve_hours_with_six_good(self):
        slots = daybook.hours_of(date(2026, 11, 2))
        self.assertEqual([slot.name for slot in slots], list(lunar.CHI))
        self.assertEqual(sum(slot.good for slot in slots), 6)
        self.assertEqual({slot.name for slot in slots if slot.good}, {hour.name for hour in lunar.good_hours(date(2026, 11, 2))})

    def test_taboos(self):
        can, chi = daybook.taboos_of(date(2026, 11, 2))
        self.assertIn("dệt cửi", can)
        self.assertIn("khóc lóc", chi)


class Sayings(unittest.TestCase):
    def setUp(self):
        self.explained, self.plain = sayings._explained(), sayings._plain()

    def test_no_duplicates(self):
        def key(text):
            return re.sub(r"[^\w ]", "", unicodedata.normalize("NFC", text).lower()).strip()
        keys = Counter(key(item.text) for item in self.explained + self.plain)
        self.assertEqual([text for text, count in keys.items() if count > 1], [])

    def test_every_entry_has_a_source(self):
        for item in self.explained + self.plain:
            self.assertTrue(item.text and item.source, item)
        for item in self.explained:
            self.assertTrue(item.meaning, item.text)

    def test_folk_sayings_are_anonymous_and_quotes_are_not(self):
        self.assertEqual({item.source for item in self.explained}, {sayings.FOLK})
        quotes = [item for item in self.plain if item.kind == "Danh ngôn"]
        self.assertNotIn(sayings.FOLK, {item.source for item in quotes})

    def test_a_year_never_repeats(self):
        self.assertEqual(math.gcd(sayings.FIRST_STEP, len(self.explained)), 1)
        self.assertEqual(math.gcd(sayings.SECOND_STEP, len(self.plain)), 1)
        self.assertGreaterEqual(len(self.plain), 366)
        days = [date(2026, 1, 1) + timedelta(days=n) for n in range(len(self.explained))]
        self.assertEqual(len({sayings.for_day(day)[0] for day in days}), len(days))

    def test_two_sayings_a_day(self):
        first, second = almanac.daily_sayings(date(2026, 11, 2))
        self.assertIn(first.kind, ("Thành ngữ", "Cổ ngữ"))
        self.assertIn(second.kind, ("Tục ngữ", "Ca dao", "Danh ngôn"))


if __name__ == "__main__":
    unittest.main()
