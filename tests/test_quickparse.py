import unittest
from datetime import datetime

from todolite.quickparse import describe, parse, parse_when, tag_prefix

# Thứ Bảy, 31/10/2026, 10:00
NOW = datetime(2026, 10, 31, 10, 0)


class Dates(unittest.TestCase):
    def check(self, text, due, title, all_day=0):
        result = parse(text, NOW)
        self.assertEqual((result["due_at"], result["title"], result["all_day"]), (due, title, all_day), text)

    def test_no_date(self):
        self.check("Mua sữa", None, "Mua sữa")

    def test_tomorrow_with_time(self):
        self.check("Nộp báo cáo mai 9h", "2026-11-01 09:00", "Nộp báo cáo")
        self.check("Nộp báo cáo ngày mai 9h30", "2026-11-01 09:30", "Nộp báo cáo")

    def test_date_only_is_all_day(self):
        self.check("Nộp báo cáo ngày mai", "2026-11-01 23:59", "Nộp báo cáo", 1)
        self.check("Trả sách 15/11", "2026-11-15 23:59", "Trả sách", 1)

    def test_numeric_date_rolls_to_next_year_when_past(self):
        self.check("Gia hạn 01/03", "2027-03-01 23:59", "Gia hạn", 1)
        self.check("Gia hạn 01/03/2028 14:00", "2028-03-01 14:00", "Gia hạn")

    def test_invalid_date_stays_in_title(self):
        self.check("Mã 31/02", None, "Mã 31/02")

    def test_leap_day_rolling_into_a_normal_year_stays_in_title(self):
        result = parse("Mã 29/02", datetime(2028, 3, 1, 8, 0))
        self.assertEqual((result["due_at"], result["title"]), (None, "Mã 29/02"))

    def test_weekdays(self):
        self.check("Họp thứ 2 9h", "2026-11-02 09:00", "Họp")
        self.check("Họp thứ hai 9h", "2026-11-02 09:00", "Họp")
        self.check("Họp t6 14:00", "2026-11-06 14:00", "Họp")
        self.check("Họp chủ nhật 8h", "2026-11-01 08:00", "Họp")
        self.check("Họp cn 8h", "2026-11-01 08:00", "Họp")

    def test_same_weekday_later_today_stays_today(self):
        self.check("Xem phim t7 20h", "2026-10-31 20:00", "Xem phim")
        self.check("Xem phim t7 8h", "2026-11-07 08:00", "Xem phim")

    def test_next_week(self):
        self.check("Họp t3 tuần sau 10h", "2026-11-03 10:00", "Họp")
        self.check("Lên kế hoạch tuần sau", "2026-11-02 23:59", "Lên kế hoạch", 1)

    def test_day_parts(self):
        self.check("Gọi điện sáng mai", "2026-11-01 09:00", "Gọi điện")
        self.check("Gọi điện chiều nay", "2026-10-31 15:00", "Gọi điện")
        self.check("Gọi điện tối nay", "2026-10-31 20:00", "Gọi điện")
        self.check("Gọi điện tối thứ 6", "2026-11-06 20:00", "Gọi điện")

    def test_day_part_words_alone_are_not_dates(self):
        self.check("Tối ưu code", None, "Tối ưu code")
        self.check("Sáng kiến mới", None, "Sáng kiến mới")

    def test_time_with_day_part(self):
        self.check("Ăn tối 7h tối", "2026-10-31 19:00", "Ăn tối")
        self.check("Chạy bộ 5h sáng mai", "2026-11-01 05:00", "Chạy bộ")
        self.check("Họp 3h chiều mai", "2026-11-01 15:00", "Họp")
        self.check("Uống thuốc 3pm", "2026-10-31 15:00", "Uống thuốc")

    def test_time_only_picks_next_future(self):
        self.check("Gọi mẹ 14:30", "2026-10-31 14:30", "Gọi mẹ")
        self.check("Tưới cây 8:00", "2026-11-01 08:00", "Tưới cây")

    def test_small_hours_mean_afternoon(self):
        self.check("Họp lúc 2h", "2026-10-31 14:00", "Họp")
        self.check("Bay lúc 02:30", "2026-11-01 02:30", "Bay")

    def test_relative(self):
        self.check("Tắt bếp sau 30p", "2026-10-31 10:30", "Tắt bếp")
        self.check("Gọi lại 2 tiếng nữa", "2026-10-31 12:00", "Gọi lại")
        self.check("Thử lại sau 3 ngày", "2026-11-03 23:59", "Thử lại", 1)

    def test_day_of_month(self):
        self.check("Đóng tiền ngày 15", "2026-11-15 23:59", "Đóng tiền", 1)
        self.check("Đóng tiền ngày 31", "2026-10-31 23:59", "Đóng tiền", 1)

    def test_month_end_and_weekend(self):
        self.check("Chốt sổ cuối tháng", "2026-10-31 23:59", "Chốt sổ", 1)
        self.check("Dọn nhà cuối tuần", "2026-10-31 23:59", "Dọn nhà", 1)

    def test_connector_words_removed(self):
        self.check("Nộp bài trước 5h chiều mai", "2026-11-01 17:00", "Nộp bài")
        self.check("Họp vào lúc 9h mai", "2026-11-01 09:00", "Họp")
        self.check("Báo cáo hạn 15/11", "2026-11-15 23:59", "Báo cáo", 1)

    def test_without_diacritics(self):
        self.check("nop bao cao mai 9h", "2026-11-01 09:00", "nop bao cao")
        self.check("hop thu 2 9h", "2026-11-02 09:00", "hop")
        self.check("goi dien chieu nay", "2026-10-31 15:00", "goi dien")
        self.check("di kham hom nay", "2026-10-31 23:59", "di kham", 1)

    def test_with_diacritics_is_strict(self):
        self.check("Thu 5 triệu tiền nhà", None, "Thu 5 triệu tiền nhà")

    def test_names_are_not_tomorrow(self):
        self.check("Gọi chị Mai", None, "Gọi chị Mai")
        self.check("Gọi chị mai", None, "Gọi chị mai")
        self.check("Gặp Mai", None, "Gặp Mai")
        self.check("Mai họp nhóm", "2026-11-01 23:59", "họp nhóm", 1)

    def test_decomposed_unicode_input(self):
        import unicodedata
        self.check(unicodedata.normalize("NFD", "Nộp báo cáo ngày mai 9h"), "2026-11-01 09:00", "Nộp báo cáo")


class Attributes(unittest.TestCase):
    def test_priority(self):
        self.assertEqual(parse("A !1", NOW)["priority"], 3)
        self.assertEqual(parse("A !2", NOW)["priority"], 2)
        self.assertEqual(parse("A !3", NOW)["priority"], 1)
        self.assertEqual(parse("A !!!", NOW)["priority"], 3)
        self.assertEqual(parse("A !cao", NOW)["priority"], 3)
        self.assertEqual(parse("A !thấp", NOW)["priority"], 1)
        self.assertEqual(parse("Chào bạn!", NOW)["priority"], 0)

    def test_tag_keeps_diacritics(self):
        result = parse("A #Công-Việc", NOW)
        self.assertEqual((result["tags"], result["title"]), (["Công-Việc"], "A"))

    def test_several_tags(self):
        result = parse("Ôn thi #học-tập #gia-đình mai", NOW)
        self.assertEqual((result["tags"], result["title"]), (["học-tập", "gia-đình"], "Ôn thi"))

    def test_tag_prefix_being_typed(self):
        self.assertEqual(tag_prefix("Họp #hoc"), "hoc")
        self.assertEqual(tag_prefix("#"), "")
        self.assertIsNone(tag_prefix("Họp #hoc "))
        self.assertIsNone(tag_prefix("Họp"))
        self.assertIsNone(tag_prefix(""))

    def test_recurrence(self):
        self.assertEqual(parse("Uống nước hằng ngày", NOW)["recur"], "daily")
        self.assertEqual(parse("Uống nước hàng ngày 9h", NOW)["recur"], "daily")
        self.assertEqual(parse("Đọc sách mỗi tuần", NOW)["recur"], "weekly")
        self.assertEqual(parse("Đóng tiền hằng tháng", NOW)["recur"], "monthly")
        self.assertEqual(parse("Chấm công ngày thường 8h", NOW)["recur"], "weekdays")

    def test_recurrence_without_date_starts_today(self):
        result = parse("Uống nước hằng ngày", NOW)
        self.assertEqual((result["due_at"], result["all_day"], result["title"]), ("2026-10-31 23:59", 1, "Uống nước"))

    def test_every_weekday(self):
        result = parse("Tập gym mỗi t2 18h", NOW)
        self.assertEqual((result["recur"], result["due_at"], result["title"]), ("weekly", "2026-11-02 18:00", "Tập gym"))

    def test_weekdays_rule_skips_weekend(self):
        self.assertEqual(parse("Chấm công ngày thường 8h", NOW)["due_at"], "2026-11-02 08:00")

    def test_block(self):
        result = parse("Viết báo cáo mai 14h ~50p", NOW)
        self.assertEqual(result["block_minutes"], 50)
        self.assertEqual(result["block_start"], "2026-11-01 14:00")
        self.assertEqual(result["title"], "Viết báo cáo")
        self.assertEqual(parse("Đọc ~1h30", NOW)["block_minutes"], 90)
        self.assertEqual(parse("Đọc ~45", NOW)["block_minutes"], 45)

    def test_full_sentence(self):
        result = parse("Tập gym t2 18h hằng tuần ~60p !2 #sức-khoẻ", NOW)
        self.assertEqual(result, {"title": "Tập gym", "due_at": "2026-11-02 18:00", "all_day": 0, "priority": 2,
                                  "tags": ["sức-khoẻ"], "recur": "weekly", "block_start": "2026-11-02 18:00",
                                  "block_minutes": 60})

    def test_only_tokens_keeps_full_text_as_title(self):
        self.assertEqual(parse("mai 9h", NOW)["title"], "mai 9h")

    def test_parse_when(self):
        self.assertEqual(parse_when("mai 9h", NOW), ("2026-11-01 09:00", 0))
        self.assertEqual(parse_when("15/11", NOW), ("2026-11-15 23:59", 1))
        self.assertIsNone(parse_when("không hiểu", NOW))

    def test_describe(self):
        text = describe(parse("Họp mai 9h !1 #việc", NOW), NOW)
        self.assertEqual(text, "Ngày mai 09:00 · Ưu tiên cao · #việc")

    def test_describe_shows_proper_tag_name(self):
        text = describe(parse("Họp #hoc-tap", NOW), NOW, tag_label=lambda name: "Học tập")
        self.assertEqual(text, "#Học tập")


if __name__ == "__main__":
    unittest.main()
