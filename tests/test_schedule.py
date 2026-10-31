import unittest
from datetime import date, datetime, timedelta

from todolite import schedule
from todolite.schedule import (CalendarItem, arrange_overlaps, calendar_items, collect, countdown, day_label, describe_event,
                               humanize, month_days, next_occurrence, summary_message, task_events, week_start)

NOW = datetime(2026, 10, 31, 10, 0)  # Thứ Bảy


def task(**fields):
    base = {"id": 1, "title": "Nộp báo cáo", "due_at": None, "all_day": 0, "remind": "30,15", "block_start": None,
            "block_minutes": 0, "snooze_until": None, "cp_total": 0, "cp_done": 0}
    return base | fields


class Recurrence(unittest.TestCase):
    def test_daily_skips_past_days(self):
        self.assertEqual(next_occurrence(datetime(2026, 10, 28, 9), "daily", NOW), datetime(2026, 11, 1, 9))

    def test_finishing_early_still_moves_past_the_due_date(self):
        self.assertEqual(next_occurrence(datetime(2026, 10, 31, 18), "daily", NOW), datetime(2026, 11, 1, 18))

    def test_weekdays_skip_weekend(self):
        self.assertEqual(next_occurrence(datetime(2026, 10, 30, 8), "weekdays", NOW), datetime(2026, 11, 2, 8))

    def test_weekly(self):
        self.assertEqual(next_occurrence(datetime(2026, 10, 26, 8), "weekly", NOW), datetime(2026, 11, 2, 8))

    def test_monthly_clamps_short_months_then_returns_to_anchor(self):
        february = next_occurrence(datetime(2027, 1, 31, 8), "monthly:31", datetime(2027, 1, 31, 9))
        self.assertEqual(february, datetime(2027, 2, 28, 8))
        self.assertEqual(next_occurrence(february, "monthly:31", datetime(2027, 3, 1)), datetime(2027, 3, 31, 8))

    def test_monthly_crosses_year(self):
        self.assertEqual(next_occurrence(datetime(2026, 12, 5, 8), "monthly:5", datetime(2026, 12, 6)), datetime(2027, 1, 5, 8))

    def test_unknown_rule(self):
        with self.assertRaises(ValueError):
            next_occurrence(NOW, "yearly", NOW)


class Events(unittest.TestCase):
    def test_deadline_events_are_sorted(self):
        kinds = [kind for _, kind, _ in task_events(task(due_at="2026-10-31 14:00"))]
        self.assertEqual(kinds, ["before:30", "before:15", "due"])

    def test_all_day_task_has_no_reminders(self):
        self.assertEqual(task_events(task(due_at="2026-10-31 23:59", all_day=1)), [])

    def test_block_events(self):
        events = task_events(task(block_start="2026-10-31 14:00", block_minutes=50))
        self.assertEqual([(moment, kind) for moment, kind, _ in events],
                         [(datetime(2026, 10, 31, 14), "block_start"), (datetime(2026, 10, 31, 14, 50), "block_end")])

    def test_changing_deadline_rearms_reminders(self):
        first = task(due_at="2026-10-31 10:10")
        show, skip, _ = collect([first], set(), NOW)
        sent = {(1, kind, stamp) for _, kind, stamp in show + skip}
        self.assertEqual(collect([first], sent, NOW)[0], [])
        moved = task(due_at="2026-10-31 10:20")
        self.assertEqual(collect([moved], sent, NOW)[0][0][1], "before:30")

    def test_extending_block_rearms_end_event(self):
        original = task(block_start="2026-10-31 09:00", block_minutes=30)
        show, skip, _ = collect([original], set(), NOW)
        sent = {(1, kind, stamp) for _, kind, stamp in show + skip}
        extended = task(block_start="2026-10-31 09:00", block_minutes=90)
        self.assertEqual(collect([extended], sent, NOW)[0], [])
        self.assertEqual(collect([extended], sent, NOW)[2], datetime(2026, 10, 31, 10, 30))


class Collect(unittest.TestCase):
    def test_only_latest_ready_event_is_shown(self):
        show, skip, _ = collect([task(due_at="2026-10-31 09:55")], set(), NOW)
        self.assertEqual([kind for _, kind, _ in show], ["due"])
        self.assertEqual(sorted(kind for _, kind, _ in skip), ["before:15", "before:30"])

    def test_next_future_event_is_reported(self):
        show, skip, upcoming = collect([task(due_at="2026-10-31 14:00")], set(), NOW)
        self.assertEqual((show, skip, upcoming), ([], [], datetime(2026, 10, 31, 13, 30)))

    def test_very_late_events_are_skipped(self):
        show, skip, _ = collect([task(due_at="2026-10-29 09:00")], set(), NOW)
        self.assertEqual(show, [])
        self.assertEqual(len(skip), 3)

    def test_startup_limit_is_stricter(self):
        stale = task(due_at="2026-10-31 09:00")
        self.assertEqual(len(collect([stale], set(), NOW)[0]), 1)
        self.assertEqual(len(collect([stale], set(), NOW, schedule.STARTUP_LATE_LIMIT)[0]), 0)

    def test_sent_events_are_ignored(self):
        item = task(due_at="2026-10-31 10:05")
        sent = {(1, "before:30", "2026-10-31 10:05"), (1, "before:15", "2026-10-31 10:05")}
        self.assertEqual(collect([item], sent, NOW)[:2], ([], []))

    def test_snooze(self):
        show, _, _ = collect([task(snooze_until="2026-10-31 09:59", remind="")], set(), NOW)
        self.assertEqual(show[0][1], "snooze")


class Grid(unittest.TestCase):
    def test_week_starts_on_monday(self):
        self.assertEqual(week_start(date(2026, 11, 1)), date(2026, 10, 26))
        self.assertEqual(week_start(date(2026, 11, 2)), date(2026, 11, 2))

    def test_month_grid_starts_monday_and_covers_month(self):
        days = month_days(2026, 11)
        self.assertEqual(days[0], date(2026, 10, 26))
        self.assertEqual(days[-1], date(2026, 12, 6))
        self.assertEqual(len(days) % 7, 0)
        self.assertEqual(days[0].weekday(), 0)

    def test_short_month_can_fit_four_weeks(self):
        self.assertEqual(len(month_days(2027, 2)), 28)

    def test_six_week_month(self):
        self.assertEqual(len(month_days(2026, 8)), 42)


class CalendarItems(unittest.TestCase):
    FIRST, LAST = date(2026, 11, 2), date(2026, 11, 9)

    def calendar_task(self, **fields):
        return task(recur="", done_at=None, remind="", **fields)

    def titles(self, *tasks):
        return [(item.start, item.kind, item.copy) for item in calendar_items(tasks, self.FIRST, self.LAST)]

    def test_deadline_becomes_a_short_event(self):
        item = calendar_items([self.calendar_task(due_at="2026-11-03 14:00")], self.FIRST, self.LAST)[0]
        self.assertEqual((item.start, item.end, item.all_day, item.kind), (datetime(2026, 11, 3, 14), datetime(2026, 11, 3, 14, 30), False, "due"))

    def test_all_day(self):
        item = calendar_items([self.calendar_task(due_at="2026-11-03 23:59", all_day=1)], self.FIRST, self.LAST)[0]
        self.assertTrue(item.all_day)

    def test_block_covers_deadline_inside_it(self):
        one = self.calendar_task(due_at="2026-11-03 14:30", block_start="2026-11-03 14:00", block_minutes=60)
        self.assertEqual(self.titles(one), [(datetime(2026, 11, 3, 14), "block", False)])

    def test_block_and_deadline_on_different_days_show_twice(self):
        one = self.calendar_task(due_at="2026-11-05 17:00", block_start="2026-11-03 14:00", block_minutes=60)
        self.assertEqual([kind for _, kind, _ in self.titles(one)], ["block", "due"])

    def test_outside_range_is_dropped(self):
        self.assertEqual(self.titles(self.calendar_task(due_at="2026-11-09 00:00")), [])

    def test_recurring_projects_future_copies(self):
        one = self.calendar_task(due_at="2026-11-03 18:00") | {"recur": "daily"}
        result = self.titles(one)
        self.assertEqual(len(result), 6)
        self.assertEqual([copy for _, _, copy in result], [False] + [True] * 5)

    def test_old_recurring_task_reaches_a_future_range(self):
        one = self.calendar_task(due_at="2026-01-06 18:00") | {"recur": "weekly"}
        self.assertEqual(self.titles(one), [(datetime(2026, 11, 3, 18), "due", True)])

    def test_monthly_copy_keeps_anchor(self):
        one = self.calendar_task(due_at="2027-01-31 09:00") | {"recur": "monthly:31"}
        result = calendar_items([one], date(2027, 3, 1), date(2027, 4, 1))
        self.assertEqual([item.start for item in result], [datetime(2027, 3, 31, 9)])

    def test_done_recurring_task_is_not_projected(self):
        one = self.calendar_task(due_at="2026-11-03 18:00") | {"recur": "daily", "done_at": "2026-11-03 19:00"}
        self.assertEqual(len(self.titles(one)), 1)

    def test_copy_moves_its_block_too(self):
        one = self.calendar_task(due_at="2026-11-03 18:30", block_start="2026-11-03 18:00", block_minutes=60) | {"recur": "weekly"}
        result = calendar_items([one], date(2026, 11, 9), date(2026, 11, 16))
        self.assertEqual([(item.start, item.kind) for item in result], [(datetime(2026, 11, 10, 18), "block")])

    def test_all_day_sorts_before_timed_on_the_same_day(self):
        timed = self.calendar_task(id=1, due_at="2026-11-03 07:00")
        whole = self.calendar_task(id=2, due_at="2026-11-03 23:59", all_day=1)
        result = calendar_items([timed, whole], self.FIRST, self.LAST)
        self.assertEqual([item.all_day for item in result], [True, False])


class Overlaps(unittest.TestCase):
    def item(self, start, end):
        base = datetime(2026, 11, 3)
        return CalendarItem({}, base + timedelta(minutes=start), base + timedelta(minutes=end), False, "due", False)

    def layout(self, *pairs):
        return [(column, columns) for _, column, columns in arrange_overlaps([self.item(*pair) for pair in pairs])]

    def test_separate_events_use_full_width(self):
        self.assertEqual(self.layout((0, 30), (30, 60), (90, 120)), [(0, 1), (0, 1), (0, 1)])

    def test_two_overlapping(self):
        self.assertEqual(self.layout((0, 60), (30, 90)), [(0, 2), (1, 2)])

    def test_three_stacked(self):
        self.assertEqual(self.layout((0, 60), (10, 60), (20, 60)), [(0, 3), (1, 3), (2, 3)])

    def test_freed_column_is_reused(self):
        self.assertEqual(self.layout((0, 60), (10, 30), (40, 70)), [(0, 2), (1, 2), (1, 2)])

    def test_empty(self):
        self.assertEqual(arrange_overlaps([]), [])


class Text(unittest.TestCase):
    def test_humanize(self):
        self.assertEqual(humanize(timedelta(minutes=14, seconds=20)), "15 phút")
        self.assertEqual(humanize(timedelta(minutes=60)), "1 giờ")
        self.assertEqual(humanize(timedelta(minutes=80)), "1 giờ 20 phút")
        self.assertEqual(humanize(timedelta(days=2)), "2 ngày")
        self.assertEqual(humanize(timedelta(days=1, hours=3)), "1 ngày 3 giờ")

    def test_countdown(self):
        self.assertEqual(countdown(timedelta(seconds=83)), "01:23")
        self.assertEqual(countdown(timedelta(hours=1, seconds=125)), "1:02:05")
        self.assertEqual(countdown(timedelta(seconds=-5)), "00:00")

    def test_day_label(self):
        today = date(2026, 10, 31)
        self.assertEqual(day_label(today, today), "Hôm nay")
        self.assertEqual(day_label(date(2026, 11, 1), today), "Ngày mai")
        self.assertEqual(day_label(date(2026, 10, 30), today), "Hôm qua")
        self.assertEqual(day_label(date(2026, 11, 3), today), "T3")
        self.assertEqual(day_label(date(2026, 12, 25), today), "25/12")
        self.assertEqual(day_label(date(2027, 1, 2), today), "02/01/2027")

    def test_reminder_uses_real_time_left(self):
        item = task(due_at="2026-10-31 10:07", cp_total=5, cp_done=2)
        self.assertEqual(describe_event(item, "before:15", NOW), ("Còn 7 phút: Nộp báo cáo", "Hạn hôm nay 10:07 · Checkpoint 2/5"))

    def test_due_and_overdue(self):
        self.assertEqual(describe_event(task(due_at="2026-10-31 10:00"), "due", NOW)[0], "Đến hạn: Nộp báo cáo")
        self.assertEqual(describe_event(task(due_at="2026-10-31 08:30"), "due", NOW)[0], "Quá hạn 1 giờ 30 phút: Nộp báo cáo")

    def test_block_messages(self):
        item = task(block_start="2026-10-31 10:00", block_minutes=50)
        self.assertEqual(describe_event(item, "block_start", NOW), ("Bắt đầu: Nộp báo cáo", "Khối 50 phút, đến 10:50"))
        self.assertEqual(describe_event(item, "block_end", NOW)[0], "Hết giờ: Nộp báo cáo")

    def test_snooze_without_deadline(self):
        self.assertEqual(describe_event(task(), "snooze", NOW)[0], "Nhắc lại: Nộp báo cáo")

    def test_summary(self):
        overdue = [task(id=1, title="A", due_at="2026-10-30 09:00")]
        today = [task(id=i, title=f"T{i}", due_at="2026-10-31 14:00") for i in range(2, 6)]
        title, lines = summary_message(overdue, today, NOW)
        self.assertEqual(title, "4 việc hôm nay · 1 quá hạn")
        self.assertEqual(lines, ["Quá hạn · A", "14:00 · T2", "14:00 · T3  (+2 việc khác)"])

    def test_summary_empty(self):
        self.assertEqual(summary_message([], [], NOW)[0], "Hôm nay chưa có việc nào")


if __name__ == "__main__":
    unittest.main()
