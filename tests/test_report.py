import os
import tempfile
import unittest
from datetime import datetime, timedelta

from todolite import pomodoro, report
from todolite.db import Store

NOW = datetime(2026, 11, 3, 14, 5)  # Thứ Ba


class ReportCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = Store(os.path.join(self.folder.name, "todo.db"))

    def tearDown(self):
        self.store.close()
        self.folder.cleanup()

    def busy_day(self):
        add = self.store.add_task
        add("Nộp hồ sơ", due_at="2026-11-01 17:00")
        add("Gọi khách", due_at="2026-11-03 11:00")
        self.meeting = add("Họp nhóm", due_at="2026-11-03 15:00")
        add("Viết báo cáo", due_at="2026-11-03 23:59", all_day=1)
        add("Thi", due_at="2026-11-04 09:00")
        add("Nộp bài", due_at="2026-11-06 10:00")
        add("Xa lắm", due_at="2026-11-11 10:00")
        add("Tập thể dục", due_at="2026-11-03 18:00", recur="daily")
        done = add("Gửi email", due_at="2026-11-03 10:00")
        self.store.complete_task(done, datetime(2026, 11, 3, 9, 12))

    def lines(self, text):
        return text.split("\n")


class Progress(ReportCase):
    def test_mid_day_report(self):
        self.busy_day()
        self.store.start_block(self.meeting, 30, NOW - timedelta(minutes=10))
        self.store.add_focus_session(None, "2026-11-03 08:00:00", 25)
        pomodoro.start(self.store, NOW - timedelta(minutes=5))
        self.assertEqual(self.lines(report.progress(self.store, NOW)), [
            "<b>Tâu Bệ hạ, tình hình đến 14:05 hôm nay</b>",
            "Đã xong 1/5 việc của hôm nay (20%), còn 3 việc, 2 việc đã trễ.",
            "Đã xong (1 việc):", "• Gửi email (09:12)",
            "Còn lại (3 việc):", "• <b>Họp nhóm</b> lúc 15:00 (còn 55 phút)", "• <b>Tập thể dục</b> lúc 18:00 (còn 3 giờ 55 phút)",
            "• <b>Viết báo cáo</b> (cả ngày)",
            "Đã trễ (2 việc):", "• Nộp hồ sơ (trễ 1 ngày)", "• Gọi khách (trễ 3 giờ 5 phút)",
            "Đang làm: <b>Họp nhóm</b>, khối giờ còn 20 phút.",
            "Pomodoro: đang tập trung, còn 20 phút; hôm nay đã xong 1 phiên (25 phút).",
            "Mốc tiếp theo: <b>Họp nhóm</b>, hạn hôm nay 15:00, còn 55 phút.",
            "Thần cúi xin Bệ hạ lo các việc trễ trước."])

    def test_numbers_follow_the_moment_of_asking(self):
        self.busy_day()
        self.assertIn("(còn 25 phút)", report.progress(self.store, NOW + timedelta(minutes=30)))

    def test_empty_day(self):
        self.assertEqual(self.lines(report.progress(self.store, NOW)),
                         ["<b>Tâu Bệ hạ, tình hình đến 14:05 hôm nay</b>", "Hôm nay chưa có việc nào đến hạn.", report.SIGN_OFF])

    def test_all_done_is_celebrated(self):
        task = self.store.add_task("Gửi email", due_at="2026-11-03 10:00")
        self.store.complete_task(task, NOW)
        self.assertTrue(report.progress(self.store, NOW).endswith("Việc trong ngày đã xong cả, thần mừng khôn xiết!"))

    def test_past_half_way(self):
        for index in range(3):
            task = self.store.add_task(f"Xong {index}", due_at="2026-11-03 10:00")
            self.store.complete_task(task, NOW)
        self.store.add_task("Còn", due_at="2026-11-03 20:00")
        self.assertTrue(report.progress(self.store, NOW).endswith("Đã quá nửa chặng đường, xin Bệ hạ giữ vững nhịp này."))

    def test_paused_pomodoro(self):
        pomodoro.start(self.store, NOW - timedelta(minutes=5))
        pomodoro.pause(self.store, NOW)
        self.assertIn("Pomodoro: đang tạm dừng, còn 20 phút.", report.progress(self.store, NOW))


class Today(ReportCase):
    def test_deadlines_of_today(self):
        self.busy_day()
        self.assertEqual(self.lines(report.today(self.store, NOW)), [
            "<b>Tâu Bệ hạ, hạn định hôm nay</b>, Thứ Ba 03/11:",
            "Đã trễ (2 việc):", "• Nộp hồ sơ (trễ 1 ngày)", "• Gọi khách (trễ 3 giờ 5 phút)",
            "Còn lại hôm nay (2 việc):", "• <b>Họp nhóm</b> lúc 15:00 (còn 55 phút)", "• <b>Viết báo cáo</b> (cả ngày)",
            "Việc thường nhật: tập thể dục.",
            "Đã xong hôm nay (1 việc): gửi email.",
            report.SIGN_OFF])

    def test_blocks_are_listed(self):
        task = self.store.add_task("Viết", due_at="2026-11-03 20:00")
        self.store.update_task(task, block_start="2026-11-03 16:00", block_minutes=90)
        self.assertIn("• 16:00–17:30 Viết", report.today(self.store, NOW))

    def test_nothing_due(self):
        self.assertIn("Hôm nay không còn hạn nào phải lo.", report.today(self.store, NOW))


class Week(ReportCase):
    def test_seven_days_by_day(self):
        self.busy_day()
        self.assertEqual(self.lines(report.week(self.store, NOW)), [
            "<b>Tâu Bệ hạ, hạn định 7 ngày tới</b> (03/11 – 09/11):",
            "Đã trễ (2 việc):", "• Nộp hồ sơ (trễ 1 ngày)", "• Gọi khách (trễ 3 giờ 5 phút)",
            "<b>Hôm nay, Thứ Ba 03/11</b> (2 việc)", "• Họp nhóm lúc 15:00", "• Viết báo cáo",
            "<b>Ngày mai, Thứ Tư 04/11</b> (1 việc)", "• Thi lúc 09:00",
            "<b>Thứ Sáu 06/11</b> (1 việc)", "• Nộp bài lúc 10:00",
            "Tổng cộng 4 việc đến hạn trong 7 ngày tới.",
            "Việc thường nhật: tập thể dục.",
            report.SIGN_OFF])

    def test_empty_week(self):
        self.store.add_task("Xa lắm", due_at="2026-11-20 10:00")
        self.assertIn("7 ngày tới chưa có hạn nào.", report.week(self.store, NOW))


class Limits(ReportCase):
    def test_long_lists_stay_inside_the_telegram_limit(self):
        for index in range(60):
            self.store.add_task(f"Việc {index} " + "rất dài " * 30, due_at="2026-11-03 20:00")
            self.store.add_task(f"Trễ {index} " + "rất dài " * 30, due_at="2026-11-02 20:00")
        for build in (report.progress, report.today, report.week):
            text = build(self.store, NOW)
            self.assertLessEqual(report._length(text), report.MESSAGE_LIMIT)
            self.assertIn("việc khác", text)

    def test_titles_are_escaped(self):
        self.store.add_task("A <b> & B", due_at="2026-11-03 20:00")
        for build in (report.progress, report.today, report.week):
            self.assertIn("A &lt;b&gt; &amp; B", build(self.store, NOW))


if __name__ == "__main__":
    unittest.main()
