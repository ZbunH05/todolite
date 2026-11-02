import unittest

from todolite.easing import (GESTURE_GAP, LINE_PIXELS, SETTLE, TOUCH_TAU, WHEEL_PAGESCROLL, WHEEL_TAU, Glide, Steps, Swipe, approach,
                             ease_out, frame_period, notch_pixels, split_touchpad, thumb_box, thumb_offset, touchpad_delta)


def run(glide, frame=1 / 90, limit=2.0):
    """Chạy tới khi dừng, trả về các vị trí và thời gian đã đi."""
    positions, elapsed = [], 0.0
    while glide.step(frame):
        positions.append(glide.position)
        elapsed += frame
        if elapsed > limit:
            raise AssertionError("không dừng")
    positions.append(glide.position)
    return positions, elapsed + frame


class TouchpadTest(unittest.TestCase):
    def test_vertical_only(self):
        self.assertEqual(split_touchpad(7), (7, 0))
        self.assertEqual(split_touchpad(65529), (-7, 0))  # -7 tới dưới dạng số 16 bit không dấu

    def test_both_axes(self):
        self.assertEqual(split_touchpad((5 << 16) | 0xFFF6), (-10, 5))
        self.assertEqual(split_touchpad((0xFFFD << 16) | 12), (12, -3))

    def test_whole_notch_stays_a_wheel(self):
        self.assertEqual(touchpad_delta(65416), (-120, False))  # nấc con lăn sau khi bàn di chuột để lại số dư
        self.assertEqual(touchpad_delta(240), (240, False))
        self.assertEqual(touchpad_delta(65529), (-7, True))
        self.assertEqual(touchpad_delta((3 << 16) | 40), (40, True))

    def test_negative_packed_value(self):
        self.assertEqual(split_touchpad(-(1 << 16) + 30), (30, -1))  # Tcl có thể trả số 32 bit có dấu


class NotchTest(unittest.TestCase):
    def test_follows_lines_setting(self):
        self.assertEqual(notch_pixels(3, 600, 1), 3 * LINE_PIXELS)
        self.assertEqual(notch_pixels(1, 600, 1.3), LINE_PIXELS * 1.3)
        self.assertEqual(notch_pixels(0, 600, 1), 0)

    def test_page_mode(self):
        self.assertEqual(notch_pixels(WHEEL_PAGESCROLL, 600, 1), 600 - LINE_PIXELS)
        self.assertEqual(notch_pixels(WHEEL_PAGESCROLL, 20, 1), LINE_PIXELS)


class CurveTest(unittest.TestCase):
    def test_ease_out(self):
        self.assertEqual(ease_out(0), 0)
        self.assertEqual(ease_out(1), 1)
        self.assertEqual(ease_out(2), 1)
        self.assertGreater(ease_out(0.5), 0.5)  # chậm dần về cuối

    def test_approach_snaps(self):
        self.assertEqual(approach(99.7, 100, 0.01, WHEEL_TAU), 100)

    def test_approach_is_time_based(self):
        """Một khung 20 ms đi đúng bằng hai khung 10 ms: khung chậm không làm chậm cả chuyển động."""
        once = approach(0, 100, 0.02, WHEEL_TAU)
        twice = approach(approach(0, 100, 0.01, WHEEL_TAU), 100, 0.01, WHEEL_TAU)
        self.assertAlmostEqual(once, twice)

    def test_frame_period(self):
        self.assertAlmostEqual(frame_period(60), 1 / 60)
        self.assertAlmostEqual(frame_period(120), 1 / 120)
        self.assertAlmostEqual(frame_period(180), 2 / 180)  # cách một nhịp, không dày hơn 125 khung mỗi giây
        self.assertAlmostEqual(frame_period(144), 2 / 144)
        self.assertAlmostEqual(frame_period(0), 1 / 60)


class GlideTest(unittest.TestCase):
    def test_one_notch_settles_in_time(self):
        glide = Glide()
        glide.reset(0, 1000)
        glide.push(108)
        positions, elapsed = run(glide)
        self.assertEqual(positions[-1], 108)
        self.assertTrue(0.12 <= elapsed <= 0.22, elapsed)
        self.assertEqual(positions, sorted(positions))

    def test_notches_accumulate(self):
        glide = Glide()
        glide.reset(0, 1000)
        glide.push(108)
        glide.step(0.03)
        glide.push(108)
        self.assertEqual(glide.target, 216)
        positions, _ = run(glide)
        self.assertEqual(positions[-1], 216)

    def test_clamps_without_overshoot(self):
        glide = Glide()
        glide.reset(950, 1000)
        glide.push(500)
        positions, _ = run(glide)
        self.assertEqual(max(positions), 1000)
        glide.push(-5000)
        positions, _ = run(glide)
        self.assertEqual(min(positions), 0)

    def test_reset_clamps(self):
        glide = Glide()
        glide.reset(1500, 1000)
        self.assertEqual(glide.position, 1000)
        glide.reset(30, -5)
        self.assertEqual((glide.position, glide.limit), (0, 0))

    def test_touchpad_follows_closely(self):
        glide = Glide()
        glide.reset(0, 1000)
        glide.push(30, TOUCH_TAU)
        glide.step(1 / 90)
        self.assertGreater(glide.position, 20)  # sau một khung đã đi hơn hai phần ba quãng

    def test_settles_crisply(self):
        glide = Glide()
        glide.reset(0, 1000)
        glide.push(108)
        positions, _ = run(glide)
        self.assertGreater(positions[-1] - positions[-2], 0)
        self.assertLessEqual(108 - positions[-2], SETTLE * 2.5)


class SwipeTest(unittest.TestCase):
    def test_small_deltas_wait_for_a_notch(self):
        swipe = Swipe()
        self.assertEqual([swipe.feed(-40, 0.01 * i) for i in range(2)], [0, 0])
        self.assertEqual(swipe.feed(-40, 0.03), 1)

    def test_one_step_per_swipe(self):
        swipe = Swipe()
        steps = [swipe.feed(-30, 0.008 * i) for i in range(150)]  # cả quán tính, tổng cộng gần 40 nấc
        self.assertEqual(sum(steps), 1)

    def test_next_swipe_after_a_pause(self):
        swipe = Swipe()
        first = sum(swipe.feed(25, 0.008 * i) for i in range(40))
        second = sum(swipe.feed(25, 1 + GESTURE_GAP + 0.008 * i) for i in range(40))
        self.assertEqual((first, second), (-1, -1))

    def test_reversal_starts_a_new_swipe(self):
        swipe = Swipe()
        self.assertEqual(sum(swipe.feed(-60, 0.01 * i) for i in range(4)), 1)
        self.assertEqual(sum(swipe.feed(60, 0.05 + 0.01 * i) for i in range(4)), -1)


class StepsTest(unittest.TestCase):
    def test_whole_lines(self):
        steps = Steps()
        self.assertEqual(steps.feed(3), 3)
        self.assertEqual([steps.feed(0.4) for _ in range(5)], [0, 0, 1, 0, 1])

    def test_direction_change_drops_remainder(self):
        steps = Steps()
        steps.feed(0.9)
        self.assertEqual(steps.feed(-0.5), 0)
        self.assertEqual(steps.feed(-0.5), -1)


class ThumbTest(unittest.TestCase):
    def test_fits(self):
        self.assertIsNone(thumb_box(0, 500, 600, 580, 32))

    def test_box(self):
        self.assertEqual(thumb_box(0, 2000, 500, 400, 32), (0, 100))
        self.assertEqual(thumb_box(1500, 2000, 500, 400, 32), (300, 100))

    def test_minimum_length(self):
        position, length = thumb_box(0, 1_000_000, 500, 400, 32)
        self.assertEqual(length, 32)

    def test_round_trip(self):
        position, length = thumb_box(700, 2000, 500, 400, 32)
        self.assertAlmostEqual(thumb_offset(position, 2000, 500, 400, length), 700)
        self.assertEqual(thumb_offset(-50, 2000, 500, 400, length), 0)
        self.assertEqual(thumb_offset(10_000, 2000, 500, 400, length), 1500)


if __name__ == "__main__":
    unittest.main()
