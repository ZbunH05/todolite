import unittest

from todolite.ui.textfit import button_shape, button_text_top, fit_parts, fit_text, side_by_side, uniform_columns

SEPARATOR = " · "


class FitText(unittest.TestCase):
    def test_short_text_is_untouched(self):
        self.assertEqual(fit_text(len, "Họp nhóm", 8), "Họp nhóm")

    def test_long_text_gets_an_ellipsis(self):
        self.assertEqual(fit_text(len, "Họp nhóm dự án", 8), "Họp nhó…")

    def test_result_never_exceeds_the_width(self):
        for width in range(1, 20):
            self.assertLessEqual(len(fit_text(len, "Viết chương 3 tài liệu", width)), width)

    def test_no_space_before_the_ellipsis(self):
        self.assertEqual(fit_text(len, "Họp nhóm dự án", 5), "Họp…")

    def test_no_room_at_all(self):
        self.assertEqual(fit_text(len, "Họp", 0), "")


class FitParts(unittest.TestCase):
    TEXT = "19 việc · 1 quá hạn · 3 đã xong"

    def test_everything_fits(self):
        self.assertEqual(fit_parts(len, self.TEXT, 40, SEPARATOR), self.TEXT)

    def test_drops_the_last_parts_first(self):
        self.assertEqual(fit_parts(len, self.TEXT, 20, SEPARATOR), "19 việc · 1 quá hạn")
        self.assertEqual(fit_parts(len, self.TEXT, 10, SEPARATOR), "19 việc")

    def test_keeps_whole_parts_only(self):
        for width in range(7, len(self.TEXT)):
            self.assertIn(fit_parts(len, self.TEXT, width, SEPARATOR), ("19 việc", "19 việc · 1 quá hạn"))

    def test_one_part_left_is_cut(self):
        self.assertEqual(fit_parts(len, self.TEXT, 5, SEPARATOR), "19 v…")

    def test_text_without_separator(self):
        self.assertEqual(fit_parts(len, "Không có dấu ngăn cách", 10, SEPARATOR), "Không có…")


class UniformColumns(unittest.TestCase):
    """Dải số liệu vẽ trên Canvas phải chia cột đúng như grid của Tk đã chia cho bản dựng bằng widget."""

    def test_widths_and_gaps_fill_the_strip(self):
        for total in range(600, 1400, 37):
            for want in (150, 234, 300):
                self.assertEqual(sum(uniform_columns(total, want, 4, 1)) + 3, total)

    def test_exact_fit_keeps_the_wanted_width(self):
        self.assertEqual(uniform_columns(4 * 200 + 3, 200, 4, 1), [200] * 4)

    def test_extra_pixels_go_to_the_later_columns(self):
        self.assertEqual(uniform_columns(4 * 200 + 3 + 1, 200, 4, 1), [200, 200, 200, 201])
        self.assertEqual(uniform_columns(4 * 200 + 3 + 2, 200, 4, 1), [200, 201, 200, 201])

    def test_shrinking_truncates_toward_zero_like_c(self):
        self.assertEqual(uniform_columns(4 * 200 + 3 - 6, 200, 4, 1), [199, 198, 199, 198])

    def test_dashboard_at_1200_pixels(self):
        """Đo trên Tk 9: thẻ rộng 936, mỗi ô cần 234, cột đầu giữ 234 còn ba cột sau 233."""
        self.assertEqual(uniform_columns(936, 234, 4, 1), [234, 233, 233, 233])


class SideBySide(unittest.TestCase):
    def test_text_first_then_what_is_left(self):
        self.assertEqual(side_by_side(164, 76, 94), (76, 88))  # biểu đồ bị ép còn 78 + 10 điểm ảnh lề, như pack

    def test_spare_room_goes_back_to_the_text(self):
        self.assertEqual(side_by_side(300, 76, 94), (206, 94))

    def test_no_room_means_nothing_after(self):
        self.assertEqual(side_by_side(60, 76, 94), (60, 0))


class ButtonLikeChip(unittest.TestCase):
    """Chip tự vẽ phải trùng từng điểm ảnh với CTkButton cũ (đã đo bằng ảnh chụp ở Cỡ chữ 1, 1.15, 1.3)."""

    def test_two_spare_pixels_all_go_below_the_label(self):
        self.assertEqual(button_text_top(26, 2, 22), 3)  # 1000/2001 của 2 điểm ảnh làm tròn xuống là 0

    def test_larger_spare_is_split_evenly(self):
        self.assertEqual(button_text_top(40, 2, 22), 2 + 6 + 1)

    def test_shape_is_floored_to_even_sizes(self):
        self.assertEqual(button_shape((48, 26), (71, 26), 1.0), [70, 26])
        self.assertEqual(button_shape((48, 26), (90, 33), 1.3), [90, 32])

    def test_asked_size_kept_when_it_still_rounds_the_same(self):
        self.assertEqual(button_shape((44, 26), (44, 26), 1.0), [44, 26])


if __name__ == "__main__":
    unittest.main()
