import os
import tempfile
import unittest
from datetime import datetime, timedelta

from todolite import pomodoro
from todolite.db import Store
from todolite.pomodoro import FOCUS, LONG, SHORT, Config, State

NOW = datetime(2026, 11, 3, 9, 0)
CFG = Config(focus=25, short=5, long=15, rounds=4, auto_break=True, auto_focus=False)


def running(phase, minutes_left=0, round_=0, task=None):
    return State(phase, NOW + timedelta(minutes=minutes_left), None, round_, task)


class Pure(unittest.TestCase):
    def test_start_runs_the_whole_phase(self):
        state = pomodoro.started(State(FOCUS, None, None, 0, None), CFG, NOW)
        self.assertEqual(state.end, NOW + timedelta(minutes=25))

    def test_pause_keeps_what_is_left_and_resume_continues(self):
        state = pomodoro.paused(running(FOCUS, 10), NOW)
        self.assertEqual((state.end, state.left), (None, 600))
        self.assertEqual(pomodoro.started(state, CFG, NOW + timedelta(hours=1)).end, NOW + timedelta(hours=1, minutes=10))

    def test_focus_then_short_break_starts_by_itself(self):
        state, session = pomodoro.finished(running(FOCUS, round_=1, task=7), CFG, NOW)
        self.assertEqual((state.phase, state.round, state.end), (SHORT, 2, NOW + timedelta(minutes=5)))
        self.assertEqual(session, pomodoro.Session(7, NOW - timedelta(minutes=25), 25))

    def test_fourth_focus_earns_the_long_break(self):
        state, _ = pomodoro.finished(running(FOCUS, round_=3), CFG, NOW)
        self.assertEqual((state.phase, state.round), (LONG, 4))

    def test_long_break_starts_a_new_round(self):
        state, session = pomodoro.finished(running(LONG, round_=4), CFG, NOW)
        self.assertEqual((state.phase, state.round, state.end, session), (FOCUS, 0, None, None))

    def test_short_break_keeps_the_count(self):
        state, _ = pomodoro.finished(running(SHORT, round_=2), CFG, NOW)
        self.assertEqual((state.phase, state.round), (FOCUS, 2))

    def test_breaks_wait_when_asked_to(self):
        state, _ = pomodoro.finished(running(FOCUS), CFG._replace(auto_break=False), NOW)
        self.assertEqual((state.phase, state.end), (SHORT, None))

    def test_focus_can_start_by_itself(self):
        state, _ = pomodoro.finished(running(SHORT), CFG._replace(auto_focus=True), NOW)
        self.assertEqual(state.end, NOW + timedelta(minutes=25))

    def test_next_phase_chains_from_the_planned_end(self):
        late = NOW + timedelta(seconds=40)  # timer của Windows tới hơi trễ
        state, _ = pomodoro.finished(running(FOCUS), CFG, late)
        self.assertEqual(state.end, NOW + timedelta(minutes=5))

    def test_after_a_long_sleep_the_break_starts_on_waking(self):
        wake = NOW + timedelta(hours=2)
        state, _ = pomodoro.finished(running(FOCUS), CFG, wake)
        self.assertEqual(state.end, wake + timedelta(minutes=5))

    def test_skip_does_not_count(self):
        self.assertEqual(pomodoro.skipped(running(FOCUS, 10, 2)), State(SHORT, None, None, 2, None))
        self.assertEqual(pomodoro.skipped(running(LONG, 10, 4)), State(FOCUS, None, None, 0, None))

    def test_reset_keeps_the_task(self):
        self.assertEqual(pomodoro.reset(running(SHORT, 3, 2, 9)), State(FOCUS, None, None, 0, 9))

    def test_seconds_left(self):
        self.assertEqual(pomodoro.seconds_left(State(LONG, None, None, 0, None), CFG, NOW), 900)
        self.assertEqual(pomodoro.seconds_left(State(FOCUS, None, 42, 0, None), CFG, NOW), 42)
        self.assertEqual(pomodoro.seconds_left(running(FOCUS, -1), CFG, NOW), 0)

    def test_notices(self):
        state = running(FOCUS, round_=1)
        new, _ = pomodoro.finished(state, CFG, NOW)
        self.assertEqual(pomodoro.notice(state, new, CFG, "Viết báo cáo"),
                         ("Xong phiên tập trung 2/4: Viết báo cáo", "Nghỉ ngắn 5 phút đã bắt đầu, đứng dậy vươn vai nhé"))
        waiting, _ = pomodoro.finished(state, CFG._replace(auto_break=False), NOW)
        self.assertEqual(pomodoro.notice(state, waiting, CFG)[1], "Bấm Bắt đầu để nghỉ ngắn 5 phút")
        last = running(FOCUS, round_=3)
        self.assertEqual(pomodoro.notice(last, pomodoro.finished(last, CFG, NOW)[0], CFG)[0], "Xong cả 4 phiên tập trung")
        rest = running(SHORT)
        self.assertEqual(pomodoro.notice(rest, pomodoro.finished(rest, CFG, NOW)[0], CFG), ("Hết giờ nghỉ", "Sẵn sàng cho phiên tập trung tiếp theo"))


class Stored(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = Store(os.path.join(self.folder.name, "todo.db"))

    def tearDown(self):
        self.store.close()
        self.folder.cleanup()

    def test_fresh_state(self):
        self.assertEqual(pomodoro.read(self.store), State(FOCUS, None, None, 0, None))
        self.assertEqual(pomodoro.config(self.store), CFG)

    def test_odd_lengths_are_kept_within_limits(self):
        self.store.set_setting("pomo_focus", "999")
        self.store.set_setting("pomo_short", "abc")
        self.assertEqual(pomodoro.config(self.store)[:2], (120, 5))

    def test_start_pause_resume_round_trip(self):
        pomodoro.start(self.store, NOW)
        self.assertEqual(pomodoro.read(self.store).end, NOW + timedelta(minutes=25))
        pomodoro.start(self.store, NOW + timedelta(minutes=1))  # bấm lần hai khi đang chạy thì không làm gì
        self.assertEqual(pomodoro.read(self.store).end, NOW + timedelta(minutes=25))
        pomodoro.pause(self.store, NOW + timedelta(minutes=5))
        self.assertEqual(pomodoro.read(self.store).left, 1200)
        pomodoro.start(self.store, NOW + timedelta(minutes=30))
        self.assertEqual(pomodoro.read(self.store).end, NOW + timedelta(minutes=50))

    def test_completing_records_the_session_once(self):
        task = self.store.add_task("Viết báo cáo")
        pomodoro.link(self.store, task)
        pomodoro.start(self.store, NOW)
        end = NOW + timedelta(minutes=25)
        self.assertIsNone(pomodoro.complete_due(self.store, end - timedelta(seconds=1)))
        self.assertEqual(pomodoro.complete_due(self.store, end)[0], "Xong phiên tập trung 1/4: Viết báo cáo")
        self.assertIsNone(pomodoro.complete_due(self.store, end))  # tiến trình thứ hai tới sau: không đếm trùng
        rows = self.store.conn.execute("SELECT task_id, started_at, minutes FROM focus_sessions").fetchall()
        self.assertEqual([tuple(row) for row in rows], [(task, "2026-11-03 09:00:00", 25)])
        state = pomodoro.read(self.store)
        self.assertEqual((state.phase, state.round, state.end), (SHORT, 1, end + timedelta(minutes=5)))
        self.assertTrue(self.store.setting("pomo_notice").startswith("2026-11-03 09:25:00|Xong phiên tập trung 1/4"))

    def test_a_deleted_task_still_counts_the_session(self):
        task = self.store.add_task("Tạm")
        pomodoro.link(self.store, task)
        pomodoro.start(self.store, NOW)
        self.store.delete_task(task)
        pomodoro.complete_due(self.store, NOW + timedelta(minutes=25))
        self.assertEqual(self.store.conn.execute("SELECT task_id FROM focus_sessions").fetchone()[0], None)

    def test_skip_stop_and_choose(self):
        pomodoro.start(self.store, NOW)
        pomodoro.skip(self.store)
        self.assertEqual(pomodoro.read(self.store), State(SHORT, None, None, 0, None))
        pomodoro.choose(self.store, LONG)
        self.assertEqual(pomodoro.read(self.store).phase, LONG)
        pomodoro.stop(self.store)
        self.assertEqual(pomodoro.read(self.store), State(FOCUS, None, None, 0, None))

    def test_focus_stats(self):
        self.store.add_focus_session(None, "2026-11-03 08:00:00", 25)
        self.store.add_focus_session(None, "2026-11-03 08:30:00", 25)
        self.store.add_focus_session(None, "2026-11-01 20:00:00", 50)
        self.store.add_focus_session(None, "2026-10-20 20:00:00", 50)
        stats = self.store.focus_stats(NOW)
        self.assertEqual((stats["count"], stats["minutes"]), (2, 50))
        self.assertEqual([minutes for _day, minutes in stats["week"]], [0, 0, 0, 0, 50, 0, 50])


if __name__ == "__main__":
    unittest.main()
