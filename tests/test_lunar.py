import unittest
from datetime import date, timedelta

from todolite import almanac, lunar
from todolite.lunar import (LunarDate, day_can_chi, day_spirit, good_hours, lunar_label, lunar_to_solar, month_can_chi, solar_term,
                            solar_to_lunar)


class Conversion(unittest.TestCase):
    def test_tet_dates(self):
        known = {2020: date(2020, 1, 25), 2021: date(2021, 2, 12), 2022: date(2022, 2, 1), 2023: date(2023, 1, 22),
                 2024: date(2024, 2, 10), 2025: date(2025, 1, 29), 2026: date(2026, 2, 17), 2027: date(2027, 2, 6),
                 2028: date(2028, 1, 26), 2029: date(2029, 2, 13)}
        for year, day in known.items():
            self.assertEqual(solar_to_lunar(day), LunarDate(1, 1, year, False), year)
            self.assertEqual(lunar_to_solar(1, 1, year), day, year)

    def test_vietnam_can_differ_from_china_by_time_zone(self):
        # Điểm sóc rơi sau 23:00 giờ Việt Nam nhưng đã sang ngày mới ở múi giờ UTC+8.
        self.assertEqual(lunar_to_solar(1, 1, 2007), date(2007, 2, 17))
        self.assertEqual(lunar_to_solar(1, 1, 2030), date(2030, 2, 2))

    def test_day_is_never_zero_when_the_true_new_moon_runs_late(self):
        for day in (date(1877, 4, 13), date(1885, 3, 16), date(2054, 5, 7), date(2062, 4, 9)):
            converted = solar_to_lunar(day)
            self.assertIn(converted.day, (29, 30), day)
            self.assertEqual(lunar_to_solar(*converted), day, day)

    def test_well_known_festivals(self):
        self.assertEqual(lunar_to_solar(10, 3, 2026), date(2026, 4, 26))  # Giỗ Tổ
        self.assertEqual(lunar_to_solar(15, 8, 2025), date(2025, 10, 6))  # Trung thu
        self.assertEqual(lunar_to_solar(15, 8, 2026), date(2026, 9, 25))

    def test_leap_months(self):
        for year, month in ((2020, 4), (2023, 2), (2025, 6), (2028, 5), (2031, 3), (2036, 6)):
            leap_day = lunar_to_solar(1, month, year, leap=True)
            self.assertIsNotNone(leap_day, year)
            self.assertEqual(solar_to_lunar(leap_day), LunarDate(1, month, year, True), year)

    def test_leap_only_exists_in_its_month(self):
        self.assertIsNone(lunar_to_solar(1, 3, 2025, leap=True))
        self.assertIsNone(lunar_to_solar(1, 6, 2026, leap=True))

    def test_impossible_lunar_dates(self):
        self.assertIsNone(lunar_to_solar(0, 1, 2026))
        self.assertIsNone(lunar_to_solar(31, 1, 2026))
        self.assertIsNone(lunar_to_solar(1, 13, 2026))

    def test_day_30_only_in_long_months(self):
        for month in range(1, 13):
            day = lunar_to_solar(29, month, 2026)
            length = lunar.lunar_month_length(day)
            self.assertIn(length, (29, 30))
            self.assertEqual(lunar_to_solar(30, month, 2026) is not None, length == 30, month)

    def test_round_trip_over_many_years(self):
        day = date(1950, 1, 1)
        while day < date(2100, 1, 1):
            converted = solar_to_lunar(day)
            self.assertEqual(lunar_to_solar(*converted), day, day)
            day += timedelta(days=1)

    def test_days_run_in_order(self):
        day = date(2000, 1, 1)
        previous = solar_to_lunar(day)
        for _ in range(11000):
            day += timedelta(days=1)
            current = solar_to_lunar(day)
            self.assertTrue(current.day == previous.day + 1 or (current.day == 1 and previous.day in (29, 30)), day)
            previous = current

    def test_label(self):
        self.assertEqual(lunar_label(date(2026, 2, 17)), "1/1")
        self.assertEqual(lunar_label(date(2026, 2, 18)), "2")

    def test_leap_text(self):
        self.assertEqual(lunar.lunar_text(LunarDate(3, 6, 2025, True)), "3 tháng 6 nhuận")
        self.assertEqual(lunar.lunar_text(LunarDate(21, 9, 2026, False)), "21 tháng 9")


class CanChi(unittest.TestCase):
    def test_years(self):
        for year, name in ((2024, "Giáp Thìn"), (2025, "Ất Tỵ"), (2026, "Bính Ngọ"), (2000, "Canh Thìn"), (1995, "Ất Hợi")):
            self.assertEqual(lunar.year_can_chi(year), name)

    def test_zodiac(self):
        self.assertEqual(lunar.year_zodiac(2026), "Ngựa")
        self.assertEqual(lunar.year_zodiac(2024), "Rồng")

    def test_first_month_follows_the_year(self):
        self.assertEqual(lunar.month_can_chi(1, 2024), "Bính Dần")  # năm Giáp
        self.assertEqual(lunar.month_can_chi(1, 2025), "Mậu Dần")  # năm Ất
        self.assertEqual(lunar.month_can_chi(1, 2026), "Canh Dần")  # năm Bính
        self.assertEqual(lunar.month_can_chi(1, 2027), "Nhâm Dần")  # năm Đinh
        self.assertEqual(lunar.month_can_chi(1, 2028), "Giáp Dần")  # năm Mậu

    def test_ninth_month(self):
        self.assertEqual(lunar.month_can_chi(9, 2026), "Mậu Tuất")

    def test_days(self):
        self.assertEqual(lunar.day_can_chi(date(2000, 1, 1)), "Mậu Ngọ")

    def test_day_cycle_is_sixty(self):
        day = date(2026, 1, 1)
        self.assertEqual(lunar.day_can_chi(day), lunar.day_can_chi(day + timedelta(days=60)))
        self.assertNotEqual(lunar.day_can_chi(day), lunar.day_can_chi(day + timedelta(days=30)))

    def test_first_hour_of_giap_day(self):
        giap = next(day for day in (date(2026, 1, 1) + timedelta(days=n) for n in range(10)) if lunar.day_can_chi(day).startswith("Giáp"))
        self.assertEqual(lunar.first_hour_can_chi(giap), "Giáp Tý")


class GoodHours(unittest.TestCase):
    TABLE = {"Tý": "Tý Sửu Mão Ngọ Thân Dậu", "Ngọ": "Tý Sửu Mão Ngọ Thân Dậu", "Sửu": "Dần Mão Tỵ Thân Tuất Hợi", "Mùi": "Dần Mão Tỵ Thân Tuất Hợi",
             "Dần": "Tý Sửu Thìn Tỵ Mùi Tuất", "Thân": "Tý Sửu Thìn Tỵ Mùi Tuất", "Mão": "Tý Dần Mão Ngọ Mùi Dậu", "Dậu": "Tý Dần Mão Ngọ Mùi Dậu",
             "Thìn": "Dần Thìn Tỵ Thân Dậu Hợi", "Tuất": "Dần Thìn Tỵ Thân Dậu Hợi", "Tỵ": "Sửu Thìn Ngọ Mùi Tuất Hợi", "Hợi": "Sửu Thìn Ngọ Mùi Tuất Hợi"}

    def test_every_day_branch_matches_the_table(self):
        for offset in range(12):
            day = date(2026, 1, 1) + timedelta(days=offset)
            branch = lunar.day_can_chi(day).split()[1]
            self.assertEqual(" ".join(hour.name for hour in lunar.good_hours(day)), self.TABLE[branch], branch)

    def test_hour_ranges(self):
        hours = {hour.name: (hour.start, hour.end) for day in (date(2026, 1, 1) + timedelta(days=n) for n in range(12)) for hour in lunar.good_hours(day)}
        self.assertEqual(hours["Tý"], (23, 1))
        self.assertEqual(hours["Sửu"], (1, 3))
        self.assertEqual(hours["Ngọ"], (11, 13))
        self.assertEqual(hours["Hợi"], (21, 23))


class Spirits(unittest.TestCase):
    def test_six_good_days_in_twelve(self):
        day = date(2026, 3, 1)
        good = sum(lunar.day_spirit(day + timedelta(days=n))[1] for n in range(12))
        self.assertEqual(good, 6)

    def test_thanh_long_starts_on_ty_in_first_month(self):
        day = next(d for d in (date(2026, 2, 17) + timedelta(days=n) for n in range(12)) if lunar.day_can_chi(d).endswith("Tý"))
        self.assertEqual(lunar.solar_to_lunar(day).month, 1)
        self.assertEqual(lunar.day_spirit(day), ("Thanh Long", True))

    def test_day_after_thanh_long(self):
        day = next(d for d in (date(2026, 2, 17) + timedelta(days=n) for n in range(12)) if lunar.day_can_chi(d).endswith("Sửu"))
        self.assertEqual(lunar.day_spirit(day), ("Minh Đường", True))


class Terms(unittest.TestCase):
    def test_start_dates_2026(self):
        known = {"Lập xuân": date(2026, 2, 4), "Xuân phân": date(2026, 3, 20), "Hạ chí": date(2026, 6, 21),
                 "Thu phân": date(2026, 9, 23), "Lập đông": date(2026, 11, 7), "Đông chí": date(2026, 12, 22)}
        for name, day in known.items():
            self.assertEqual(lunar.solar_term(day), name, name)
            self.assertNotEqual(lunar.solar_term(day - timedelta(days=1)), name, name)

    def test_every_term_appears_in_a_year(self):
        names = {lunar.solar_term(date(2026, 1, 1) + timedelta(days=n)) for n in range(365)}
        self.assertEqual(names, set(lunar.SOLAR_TERMS))

    def test_next_term(self):
        self.assertEqual(lunar.next_solar_term(date(2026, 11, 1)), ("Lập đông", date(2026, 11, 7)))

    def test_late_december_is_not_autumn(self):
        self.assertEqual(lunar.solar_term(date(2026, 12, 25)), "Đông chí")


class Events(unittest.TestCase):
    def test_solar(self):
        self.assertIn("Ngày Quốc khánh", almanac.events_on(date(2026, 9, 2)))

    def test_lunar(self):
        self.assertIn("Tết Nguyên Đán", almanac.events_on(date(2026, 2, 17)))
        self.assertIn("Tết Trung thu", almanac.events_on(date(2026, 9, 25)))

    def test_leap_month_has_no_duplicate_festival(self):
        leap_fifteenth = lunar_to_solar(15, 6, 2025, leap=True)
        self.assertNotIn("Lễ Vu Lan", almanac.events_on(leap_fifteenth))

    def test_mothers_and_fathers_day_float(self):
        self.assertIn("Ngày của Mẹ", almanac.events_on(date(2026, 5, 10)))
        self.assertIn("Ngày của Cha", almanac.events_on(date(2026, 6, 21)))
        self.assertNotIn("Ngày của Mẹ", almanac.events_on(date(2026, 5, 13)))

    def test_new_years_eve_is_the_last_lunar_day(self):
        self.assertIn("Giao thừa", almanac.events_on(date(2026, 2, 16)))
        self.assertIn("Giao thừa", almanac.events_on(date(2025, 1, 28)))

    def test_month_list_is_ordered(self):
        events = almanac.month_events(2026, 11)
        self.assertEqual([day for day, _ in events], sorted(day for day, _ in events))
        self.assertIn((date(2026, 11, 20), "Ngày Nhà giáo Việt Nam"), events)

    def test_saying_changes_daily(self):
        day = date(2026, 11, 1)
        self.assertNotEqual(almanac.daily_saying(day), almanac.daily_saying(day + timedelta(days=1)))
        self.assertEqual(almanac.daily_saying(day), almanac.daily_saying(day))


class Sources(unittest.TestCase):
    """Giá trị đối chiếu với baohatinh.vn, xemlicham.com và ngaydep.com, không suy ra từ chính code này."""
    DAYS = ((date(2026, 11, 1), LunarDate(23, 9, 2026, False), "Kỷ Mão", "Mậu Tuất", ("Câu Trần", False),
             ("Tý", "Dần", "Mão", "Ngọ", "Mùi", "Dậu"), "Sương giáng"),
            (date(2026, 11, 11), LunarDate(3, 10, 2026, False), "Kỷ Sửu", "Kỷ Hợi", ("Ngọc Đường", True),
             ("Dần", "Mão", "Tỵ", "Thân", "Tuất", "Hợi"), "Lập đông"),
            (date(2026, 11, 17), LunarDate(9, 10, 2026, False), "Ất Mùi", "Kỷ Hợi", ("Minh Đường", True),
             ("Dần", "Mão", "Tỵ", "Thân", "Tuất", "Hợi"), "Lập đông"))

    def test_published_days(self):
        for day, converted, day_name, month_name, spirit, hours, term in self.DAYS:
            with self.subTest(day):
                self.assertEqual(solar_to_lunar(day), converted)
                self.assertEqual(day_can_chi(day), day_name)
                self.assertEqual(month_can_chi(converted.month, converted.year), month_name)
                self.assertEqual(day_spirit(day), spirit)
                self.assertEqual(tuple(hour.name for hour in good_hours(day)), hours)
                self.assertEqual(solar_term(day), term)

    def test_published_day_without_spirit(self):
        day = date(2026, 12, 19)
        self.assertEqual(solar_to_lunar(day), LunarDate(11, 11, 2026, False))
        self.assertEqual(day_can_chi(day), "Đinh Mão")
        self.assertEqual(month_can_chi(11, 2026), "Canh Tý")
        self.assertEqual(tuple(hour.name for hour in good_hours(day)), ("Tý", "Dần", "Mão", "Ngọ", "Mùi", "Dậu"))

    def test_vietnam_was_a_whole_month_ahead_of_china_in_1985(self):
        self.assertEqual(lunar_to_solar(1, 1, 1985), date(1985, 1, 21))

    def test_leap_months_where_vietnam_differs_from_china(self):
        self.assertEqual(solar_to_lunar(date(1985, 3, 21)), LunarDate(1, 2, 1985, True))
        self.assertEqual(solar_to_lunar(date(1987, 7, 26)), LunarDate(1, 7, 1987, False))
        self.assertEqual(solar_to_lunar(date(1987, 8, 24)), LunarDate(1, 7, 1987, True))


if __name__ == "__main__":
    unittest.main()
