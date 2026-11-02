import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from todolite import remind
from todolite.db import Store
from todolite.schedule import telegram_reminders, to_text

NOW = datetime(2026, 11, 3, 9, 0)  # Thứ Ba
EARLIER = "2026-11-01 08:00"


class FakeTelegram(BaseHTTPRequestHandler):
    sent = []
    statuses = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        status, reply = FakeTelegram.statuses.pop(0) if FakeTelegram.statuses else (200, {"ok": True, "result": {"message_id": 1}})
        if status == 200:
            FakeTelegram.sent.append(body)
        raw = json.dumps(reply).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        pass


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = Store(os.path.join(self.folder.name, "todo.db"))

    def tearDown(self):
        self.store.close()
        self.folder.cleanup()

    def add(self, title, due, created=EARLIER, **fields):
        task_id = self.store.add_task(title, due_at=due, **fields)
        self.store.conn.execute("UPDATE tasks SET created_at=? WHERE id=?", (created, task_id))
        return task_id

    def check(self, now, offsets=(1440, 60, 15)):
        send, skip, upcoming = telegram_reminders(self.store.scheduled_tasks(), offsets, self.store.sent_keys(), now)
        return [(task["id"], kind) for task, kind, _ in send], [(task["id"], kind) for task, kind, _ in skip], upcoming


class Rules(StoreCase):
    def test_each_offset_fires_on_time(self):
        task = self.add("Họp", "2026-11-03 10:00")
        self.assertEqual(self.check(NOW)[:2], ([(task, "tg:60")], [(task, "tg:1440")]))
        self.assertEqual(self.check(datetime(2026, 11, 3, 9, 45))[0], [(task, "tg:15")])

    def test_next_moment_is_reported_for_the_timer(self):
        self.add("Họp", "2026-11-04 10:00")
        self.assertEqual(self.check(NOW)[2], datetime(2026, 11, 3, 10, 0))

    def test_sent_reminders_stay_sent_until_the_deadline_moves(self):
        task = self.add("Họp", "2026-11-03 10:00")
        send, skip, _ = telegram_reminders(self.store.scheduled_tasks(), (60,), self.store.sent_keys(), NOW)
        self.store.mark_sent(send + skip)
        self.assertEqual(self.check(NOW, (60,))[0], [])
        self.store.update_task(task, due_at="2026-11-03 09:30")
        self.assertEqual(self.check(NOW, (30,))[0], [(task, "tg:30")])

    def test_all_day_tasks_wait_for_the_morning_brief(self):
        self.add("Nộp hồ sơ", "2026-11-04 23:59", all_day=1)
        self.assertEqual(self.check(datetime(2026, 11, 3, 23, 59)), ([], [], None))

    def test_nothing_for_a_task_made_after_the_moment(self):
        task = self.add("Gọi điện", "2026-11-03 09:20", created="2026-11-03 09:00")
        send, skip, upcoming = self.check(NOW, (30, 15))
        self.assertEqual((send, skip), ([], [(task, "tg:30")]))
        self.assertEqual(upcoming, datetime(2026, 11, 3, 9, 5))

    def test_old_moments_are_dropped_after_the_pc_slept(self):
        task = self.add("Họp", "2026-11-03 10:00")
        self.assertEqual(self.check(datetime(2026, 11, 3, 9, 30), (60,))[:2], ([], [(task, "tg:60")]))

    def test_a_long_offset_may_arrive_a_little_late(self):
        task = self.add("Nộp bài", "2026-11-04 09:00")
        self.assertEqual(self.check(NOW + timedelta(hours=5), (1440,))[0], [(task, "tg:1440")])  # 6 giờ cho mốc 1 ngày

    def test_never_after_the_deadline(self):
        task = self.add("Họp", "2026-11-03 08:55")
        self.assertEqual(self.check(NOW, (15,))[:2], ([], [(task, "tg:15")]))

    def test_done_tasks_are_left_alone(self):
        task = self.add("Họp", "2026-11-03 10:00")
        self.store.complete_task(task, NOW)
        self.assertEqual(self.check(NOW), ([], [], None))


class Message(StoreCase):
    def events(self, now, offsets=(60,)):
        return telegram_reminders(self.store.scheduled_tasks(), offsets, set(), now)[0]

    def test_one_task(self):
        self.add("Nộp <báo cáo>", "2026-11-03 10:00")
        self.assertEqual(remind.build(self.events(NOW), NOW),
                         "<b>Tâu Bệ hạ, còn 1 giờ là tới hạn:</b>\n• <b>Nộp &lt;báo cáo&gt;</b>, hạn hôm nay 10:00")

    def test_several_tasks_in_one_message(self):
        self.add("B", "2026-11-03 10:00")
        self.add("A", "2026-11-03 09:58")
        text = remind.build(self.events(NOW, (60, 15)), NOW)
        self.assertEqual(text.split("\n"), ["<b>Tâu Bệ hạ, có 2 việc sắp tới hạn:</b>", "• <b>A</b>, hạn hôm nay 09:58 (còn 58 phút)",
                                            "• <b>B</b>, hạn hôm nay 10:00 (còn 1 giờ)"])

    def test_tomorrow_reads_naturally(self):
        self.add("Thi", "2026-11-04 09:00")
        self.assertIn("hạn ngày mai 09:00", remind.build(self.events(NOW, (1440,)), NOW))

    def test_long_lists_are_capped(self):
        for index in range(remind.MAX_ITEMS + 3):
            self.add(f"Việc {index}", "2026-11-03 10:00")
        self.assertTrue(remind.build(self.events(NOW), NOW).endswith("• và 3 việc khác"))


class Sending(StoreCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeTelegram)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        super().setUp()
        FakeTelegram.sent, FakeTelegram.statuses = [], []
        self.store.set_secret("telegram_token", "123:SECRET")
        self.store.set_setting("telegram_chat_id", "42")
        self.store.set_setting("telegram_api_url", f"http://127.0.0.1:{self.server.server_port}")
        self.store.set_setting("telegram_remind", "60")
        patcher = mock.patch.object(remind, "log")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.task = self.add("Họp", "2026-11-03 10:00")

    def run_it(self, now=NOW):
        waits = []
        return remind.send_due(self.store, now, wait=waits.append), waits

    def test_sends_once(self):
        self.assertEqual(self.run_it(), (True, []))
        self.assertEqual(self.run_it(), (False, []))
        self.assertEqual(len(FakeTelegram.sent), 1)
        self.assertEqual(FakeTelegram.sent[0]["chat_id"], "42")

    def test_network_trouble_leaves_it_for_the_next_try(self):
        failure = (502, {"ok": False, "error_code": 502, "description": "Bad Gateway"})
        FakeTelegram.statuses = [failure] * remind.ATTEMPTS
        self.assertEqual(self.run_it(), (False, [remind.RETRY_DELAY] * (remind.ATTEMPTS - 1)))
        self.assertEqual(self.run_it(), (True, []))

    def test_wrong_token_gives_up_and_says_why(self):
        FakeTelegram.statuses = [(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})]
        self.assertEqual(self.run_it(), (False, []))
        self.assertIn("Bot Token", self.store.setting("telegram_status"))
        self.assertEqual(self.run_it(), (False, []))  # không thử mãi với cấu hình sai

    def test_turned_off(self):
        self.store.set_setting("telegram_remind", "")
        self.assertEqual(self.run_it(), (False, []))
        self.assertEqual(FakeTelegram.sent, [])


if __name__ == "__main__":
    unittest.main()
