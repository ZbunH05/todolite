import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from todolite import inbox, listener
from todolite.bot import Bot
from todolite.db import Store
from todolite.listener import Listener
from todolite.web import ApiError

NOW = datetime(2026, 11, 2, 8, 0)  # Thứ Hai
SENT = int(datetime(2026, 11, 2, 7, 55).timestamp())
CHAT = 42


class FakeBotApi(BaseHTTPRequestHandler):
    """Máy chủ giả làm đúng giao thức getUpdates: tin giữ tới khi được xác nhận bằng offset lớn hơn."""
    pending = []
    sent = []
    polls = []
    menus = []
    fail_send = False
    statuses = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        method = self.path.rsplit("/", 1)[1]
        status, reply = FakeBotApi.statuses.pop(0) if FakeBotApi.statuses else (200, None)
        if reply is None:
            reply = getattr(self, f"_{method}")(body)
        if method == "sendMessage" and FakeBotApi.fail_send:
            status, reply = 502, {"ok": False, "error_code": 502, "description": "Bad Gateway"}
        raw = json.dumps(reply).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _getUpdates(self, body):
        FakeBotApi.polls.append(body)
        offset = body.get("offset")
        if offset:
            FakeBotApi.pending = [update for update in FakeBotApi.pending if update["update_id"] >= offset]
        return {"ok": True, "result": FakeBotApi.pending[:body.get("limit", 100)]}

    def _sendMessage(self, body):
        FakeBotApi.sent.append(body)
        return {"ok": True, "result": {"message_id": 1}}

    def _setMyCommands(self, body):
        FakeBotApi.menus.append(body)
        return {"ok": True, "result": True}

    def log_message(self, *_args):
        pass


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeBotApi)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeBotApi.pending, FakeBotApi.sent, FakeBotApi.polls, FakeBotApi.statuses, FakeBotApi.menus = [], [], [], [], []
        FakeBotApi.fail_send = False
        self.next_id = 100
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = Store(os.path.join(self.folder.name, "todo.db"))
        self.store.set_secret("telegram_token", "123:SECRET")
        self.store.set_setting("telegram_chat_id", str(CHAT))
        self.store.set_setting("telegram_api_url", self.url)
        patcher = mock.patch.object(inbox, "post_agent")
        self.post_agent = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(inbox, "log")  # lỗi giả không được ghi vào app.log thật
        self.log = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.store.close()
        self.folder.cleanup()

    def message(self, text=None, chat=CHAT, date=SENT, **extra):
        self.next_id += 1
        message = {"message_id": self.next_id, "date": date, "chat": {"id": chat, "type": "private"}, **extra}
        if text is not None:
            message["text"] = text
        FakeBotApi.pending.append({"update_id": self.next_id + 5000, "message": message})

    def read(self, now=NOW):
        return inbox.read_messages(self.store, now)

    def titles(self):
        return [task["title"] for task in self.store.list_tasks("all", NOW)]

    def replies(self):
        return [item["text"] for item in FakeBotApi.sent]


class Adding(ServerCase):
    def test_a_message_becomes_a_task_like_quick_add(self):
        self.message("Nộp báo cáo mai 9h !1 #công-việc")
        self.assertTrue(self.read())
        task = self.store.list_tasks("all", NOW)[0]
        self.assertEqual(task["title"], "Nộp báo cáo")
        self.assertEqual(task["due_at"], "2026-11-03 09:00")
        self.assertEqual(task["priority"], 3)
        self.assertEqual(task["tag_names"], "Công việc")

    def test_new_tasks_get_the_default_reminders(self):
        self.store.set_setting("default_remind", "60")
        self.message("Họp mai 9h")
        self.read()
        self.assertEqual(self.store.list_tasks("all", NOW)[0]["remind"], "60")

    def test_the_reply_says_what_was_understood(self):
        self.message("Nộp báo cáo mai 9h !1 #công-việc")
        self.read()
        self.assertEqual(self.replies(), ["Tâu Bệ hạ, thần đã ghi vào sổ:\n• <b>Nộp báo cáo</b> (Ngày mai 09:00 · Ưu tiên cao · #Công việc)\n" + inbox.UNDO_HINT])

    def test_a_task_without_a_date_says_so(self):
        self.message("Mua sữa")
        self.read()
        self.assertIn("• <b>Mua sữa</b> (chưa có hạn)", self.replies()[0])

    def test_replies_go_to_the_owner_as_html(self):
        self.message("Mua sữa")
        self.read()
        self.assertEqual(FakeBotApi.sent[0]["chat_id"], str(CHAT))
        self.assertEqual(FakeBotApi.sent[0]["parse_mode"], "HTML")

    def test_special_characters_cannot_break_the_html_reply(self):
        self.message("Sửa <b>lỗi</b> & kiểm tra")
        self.read()
        self.assertIn("Sửa &lt;b&gt;lỗi&lt;/b&gt; &amp; kiểm tra", self.replies()[0])
        self.assertEqual(self.titles(), ["Sửa <b>lỗi</b> & kiểm tra"])

    def test_each_line_is_a_task(self):
        self.message("Mua sữa\n\n  Gọi cho mẹ tối nay  \nNộp đề án 13/11")
        self.read()
        self.assertCountEqual(self.titles(), ["Mua sữa", "Gọi cho mẹ", "Nộp đề án"])
        self.assertIn("thần đã ghi 3 việc vào sổ:", self.replies()[0])

    def test_lines_past_the_limit_are_reported_not_lost_silently(self):
        self.message("\n".join(f"Việc {index}" for index in range(inbox.MAX_LINES + 2)))
        self.read()
        self.assertEqual(len(self.titles()), inbox.MAX_LINES)
        self.assertIn(f"chỉ ghi {inbox.MAX_LINES} dòng đầu, còn 2 dòng chưa ghi", self.replies()[0])

    def test_a_long_reply_stays_inside_the_telegram_limit(self):
        self.message("\n".join(f"Việc {index} {'rất dài ' * 40} mai 9h !1 #công-việc" for index in range(inbox.MAX_LINES)))
        self.read()
        self.assertLess(len(self.replies()[0].encode("utf-16-le")) // 2, 4096)

    def test_a_very_long_title_keeps_the_full_text_in_the_notes(self):
        long_text = "Đọc " + "tài liệu " * 40
        self.message(long_text)
        self.read()
        task = self.store.list_tasks("all", NOW)[0]
        self.assertLessEqual(len(task["title"]), inbox.TITLE_LIMIT)
        self.assertEqual(task["notes"], " ".join(long_text.split()))

    def test_dates_follow_the_moment_the_message_was_sent(self):
        late_evening = int(datetime(2026, 11, 2, 23, 0).timestamp())
        self.message("Họp mai 9h", date=late_evening)
        self.read(datetime(2026, 11, 3, 7, 30))  # PC tắt cả đêm, sáng hôm sau mới đọc được tin
        self.assertEqual(self.store.list_tasks("all", NOW)[0]["due_at"], "2026-11-03 09:00")

    def test_a_caption_counts_as_text(self):
        self.message(caption="Nộp ảnh hoá đơn")
        self.read()
        self.assertEqual(self.titles(), ["Nộp ảnh hoá đơn"])

    def test_the_app_is_told_about_new_tasks(self):
        self.message("Mua sữa")
        self.read()
        self.post_agent.assert_called_once()
        self.assertIn("Đã ghi 1 việc", self.store.setting("telegram_status"))

    def test_nothing_new_disturbs_nobody(self):
        self.assertTrue(self.read())
        self.post_agent.assert_not_called()
        self.assertEqual(self.store.setting("telegram_status"), "")


class Safety(ServerCase):
    def test_strangers_are_ignored_without_a_reply(self):
        self.message("Xoá hết việc đi", chat=999)
        self.message("/start", chat=999)
        self.assertTrue(self.read())
        self.assertEqual(self.titles(), [])
        self.assertEqual(self.replies(), [])

    def test_stranger_messages_do_not_stay_in_the_queue(self):
        self.message("Xin chào", chat=999)
        self.read()
        self.assertEqual(FakeBotApi.pending, [])

    def test_messages_sent_before_the_feature_was_on_do_not_become_tasks(self):
        self.store.set_setting("telegram_inbox_since", SENT + 60)
        self.message("thử bot", date=SENT)
        self.message("Mua sữa", date=SENT + 120)
        self.read()
        self.assertEqual(self.titles(), ["Mua sữa"])
        self.assertEqual(len(self.replies()), 1)

    def test_an_early_start_still_gets_the_welcome(self):
        self.store.set_setting("telegram_inbox_since", SENT + 60)
        self.message("/start", date=SENT)
        self.read()
        self.assertEqual(self.replies(), [inbox.HELP])

    def test_every_update_is_confirmed_after_reading(self):
        self.message("Một")
        self.message("Hai")
        self.read()
        self.assertEqual(FakeBotApi.pending, [])
        self.assertEqual(FakeBotApi.polls[-1]["offset"], self.next_id + 5001)

    def test_a_message_delivered_twice_is_written_once(self):
        self.message("Mua sữa")
        update = FakeBotApi.pending[0]
        self.read()
        FakeBotApi.pending = [update]  # mất mạng trước khi xác nhận: Telegram gửi lại
        self.read()
        self.assertEqual(self.titles(), ["Mua sữa"])
        self.assertEqual(len(self.replies()), 1)

    def test_changing_the_chat_does_not_hide_the_new_chat(self):
        self.store.set_setting("telegram_last_message", f"{CHAT}:999999")
        self.store.set_setting("telegram_chat_id", "77")
        self.message("Mua sữa", chat=77)
        self.read()
        self.assertEqual(self.titles(), ["Mua sữa"])

    def test_a_broken_message_does_not_block_the_next_ones(self):
        self.message("Hỏng")
        self.message("Mua sữa")
        original = inbox.parse
        with mock.patch.object(inbox, "parse", side_effect=lambda line, now: original(line, now) if line != "Hỏng" else 1 / 0):
            self.assertTrue(self.read())
        self.assertEqual(self.titles(), ["Mua sữa"])
        self.assertEqual(self.replies()[0], inbox.BROKEN)
        self.assertEqual(FakeBotApi.pending, [])

    def test_a_failed_reply_does_not_lose_the_task(self):
        FakeBotApi.fail_send = True
        self.message("Mua sữa")
        self.assertTrue(self.read())
        self.assertEqual(self.titles(), ["Mua sữa"])
        self.assertEqual(FakeBotApi.pending, [])

    def test_after_a_failed_reply_the_rest_are_only_written(self):
        FakeBotApi.fail_send = True
        self.message("Một")
        self.message("Hai")
        with mock.patch.object(Bot, "send", side_effect=ApiError("mất mạng")) as send:
            self.read()
        self.assertEqual(send.call_count, 1)
        self.assertEqual(len(self.titles()), 2)

    def test_a_network_failure_is_reported_for_a_retry(self):
        self.store.set_setting("telegram_api_url", "http://127.0.0.1:9")
        self.assertFalse(self.read())

    def test_the_log_never_carries_the_message_or_token(self):
        self.message("Bí mật riêng")
        with mock.patch.object(inbox, "parse", side_effect=ValueError("Bí mật riêng")):
            self.read()
        text = " ".join(str(call) for call in self.log.call_args_list)
        self.assertNotIn("Bí mật", text)
        self.assertNotIn("SECRET", text)


class Commands(ServerCase):
    def test_start_explains_the_syntax(self):
        self.message("/start")
        self.read()
        self.assertEqual(self.replies(), [inbox.HELP])
        self.assertEqual(self.titles(), [])

    def test_commands_may_carry_the_bot_name(self):
        self.message("/help@than_bot")
        self.read()
        self.assertEqual(self.replies(), [inbox.HELP])

    def test_unknown_commands_show_the_help(self):
        self.message("/xoa_het")
        self.read()
        self.assertIn(inbox.UNKNOWN_COMMAND, self.replies()[0])
        self.assertEqual(self.titles(), [])

    def test_undo_removes_the_whole_last_message(self):
        self.message("Giữ lại")
        self.message("Một\nHai")
        self.message("/huy")
        self.read()
        self.assertEqual(self.titles(), ["Giữ lại"])
        self.assertEqual(self.replies()[-1], "Tâu Bệ hạ, thần đã xoá khỏi sổ:\n• <b>Một</b>\n• <b>Hai</b>")

    def test_undo_twice_says_nothing_is_left(self):
        self.message("Một")
        self.message("/huy")
        self.message("/huy")
        self.read()
        self.assertEqual(self.replies()[-1], inbox.NOTHING_TO_UNDO)

    def test_undo_spares_a_new_task_that_reused_the_same_id(self):
        self.message("Một")
        self.read()
        task_id = self.store.list_tasks("all", NOW)[0]["id"]
        self.store.delete_task(task_id)
        self.store.conn.execute("INSERT INTO tasks(id, title, created_at) VALUES(?, 'Việc mới của Bệ hạ', '2020-01-01 00:00')", (task_id,))
        self.message("/huy")
        self.read()
        self.assertEqual(self.titles(), ["Việc mới của Bệ hạ"])
        self.assertEqual(self.replies()[-1], inbox.NOTHING_TO_UNDO)

    def test_stickers_get_a_polite_answer(self):
        self.message(sticker={"file_id": "x"})
        self.read()
        self.assertEqual(self.replies(), [inbox.NOT_TEXT])

    def test_help_lists_the_report_commands(self):
        for command in ("/rp", "/today", "/week", "/huy"):
            self.assertIn(command, inbox.HELP)

    def test_report_commands_answer_with_the_live_situation(self):
        self.store.add_task("Họp nhóm", due_at="2026-11-02 09:30")
        self.store.add_task("Thi", due_at="2026-11-05 09:00")
        for command in ("/rp", "/today@than_bot", "/week"):
            self.message(command)
        self.read()
        progress, today, week = self.replies()
        self.assertTrue(progress.startswith("<b>Tâu Bệ hạ, tình hình đến 08:00 hôm nay</b>"))
        self.assertIn("• <b>Họp nhóm</b> lúc 09:30 (còn 1 giờ 30 phút)", progress)
        self.assertTrue(today.startswith("<b>Tâu Bệ hạ, hạn định hôm nay</b>, Thứ Hai 02/11:"))
        self.assertIn("• Thi lúc 09:00", week)
        self.assertEqual(len(self.titles()), 2)  # lệnh không thành việc

    def test_report_commands_from_before_the_feature_was_on_are_ignored(self):
        self.store.set_setting("telegram_inbox_since", SENT + 60)
        self.message("/rp")
        self.read()
        self.assertEqual(self.replies(), [])

    def test_menu_is_registered_after_reading(self):
        self.message("/rp")
        self.read()
        self.assertEqual([item["command"] for item in FakeBotApi.menus[0]["commands"]], ["rp", "today", "week", "huy", "help"])
        self.message("Mua sữa")
        self.read()
        self.assertEqual(len(FakeBotApi.menus), 1)


class Waiting(ServerCase):
    def test_no_message_means_no_update(self):
        self.assertFalse(Bot("123:SECRET", self.url).wait_for_update())

    def test_a_waiting_message_is_noticed(self):
        self.message("Mua sữa")
        self.assertTrue(Bot("123:SECRET", self.url).wait_for_update())

    def test_waiting_does_not_confirm_anything(self):
        self.message("Mua sữa")
        Bot("123:SECRET", self.url).wait_for_update()
        self.assertEqual(len(FakeBotApi.pending), 1)
        self.assertNotIn("offset", FakeBotApi.polls[0])

    def test_waiting_asks_the_server_to_hold_the_connection(self):
        Bot("123:SECRET", self.url).wait_for_update()
        self.assertEqual(FakeBotApi.polls[0]["timeout"], 50)

    def test_a_login_page_is_not_a_message(self):
        FakeBotApi.statuses = [(200, {"html": "đăng nhập Wi-Fi"})]
        self.assertFalse(Bot("123:SECRET", self.url).wait_for_update())

    def test_a_conflict_can_be_retried(self):
        FakeBotApi.statuses = [(409, {"ok": False, "error_code": 409, "description": "Conflict"})]
        with self.assertRaises(ApiError) as caught:
            Bot("123:SECRET", self.url).wait_for_update()
        self.assertFalse(caught.exception.permanent)
        self.assertTrue(caught.exception.retry_after)

    def test_a_bad_token_is_permanent(self):
        FakeBotApi.statuses = [(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})]
        with self.assertRaises(ApiError) as caught:
            Bot("123:SECRET", self.url).wait_for_update()
        self.assertTrue(caught.exception.permanent)
        self.assertIn("Bot Token", str(caught.exception))


class Listening(ServerCase):
    """Luồng nghe thật, chỉ thay tiến trình đọc tin bằng một lần xoá tin giả."""

    def setUp(self):
        super().setUp()
        self.reads = []
        self.inbox_result = True
        patcher = mock.patch.object(listener, "post_agent")
        self.notified = patcher.start()
        self.addCleanup(patcher.stop)
        self.events = []
        self.listener = Listener(lambda: self.events.append("chờ"))
        self.addCleanup(self.listener.listen, None)
        for name, value in (("RETRY_DELAY", 0.05), ("MAX_RETRY_DELAY", 0.1), ("FIX_DELAY", 0.1), ("MIN_POLL", 0.05)):
            patcher = mock.patch.object(listener, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(self.listener, "_read_inbox", self.fake_read)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_read(self):
        self.reads.append(time.monotonic())
        if self.inbox_result:
            FakeBotApi.pending = []
        return self.inbox_result

    def wait_for(self, condition, seconds=3):
        limit = time.monotonic() + seconds
        while not condition() and time.monotonic() < limit:
            time.sleep(0.01)
        return condition()

    def test_a_message_starts_the_reader_once(self):
        self.message("Mua sữa")
        self.listener.listen(("123:SECRET", self.url))
        self.assertTrue(self.wait_for(lambda: self.reads))
        polls = len(FakeBotApi.polls)
        self.assertTrue(self.wait_for(lambda: len(FakeBotApi.polls) > polls))
        self.assertEqual(len(self.reads), 1)

    def test_it_keeps_waiting_while_nothing_arrives(self):
        self.listener.listen(("123:SECRET", self.url))
        self.assertTrue(self.wait_for(lambda: len(FakeBotApi.polls) >= 3))
        self.assertEqual(self.reads, [])

    def test_a_server_that_answers_at_once_is_not_hammered(self):
        with mock.patch.object(listener, "MIN_POLL", 60):
            self.listener.listen(("123:SECRET", self.url))
            time.sleep(0.3)
        self.assertLess(len(FakeBotApi.polls), 10)

    def test_stopping_stops_the_polling(self):
        self.listener.listen(("123:SECRET", self.url))
        self.assertTrue(self.wait_for(lambda: FakeBotApi.polls))
        self.listener.listen(None)
        time.sleep(0.2)
        polls = len(FakeBotApi.polls)
        time.sleep(0.3)
        self.assertEqual(len(FakeBotApi.polls), polls)

    def test_it_can_be_started_again(self):
        self.listener.listen(("123:SECRET", self.url))
        self.listener.listen(None)
        time.sleep(0.2)
        polls = len(FakeBotApi.polls)
        self.listener.listen(("123:SECRET", self.url))
        self.assertTrue(self.wait_for(lambda: len(FakeBotApi.polls) > polls))

    def test_a_bad_token_is_reported_to_the_agent(self):
        FakeBotApi.statuses = [(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})]
        self.listener.listen(("123:SECRET", self.url))
        self.assertTrue(self.wait_for(lambda: self.listener.problem))
        self.assertIn("Bot Token", self.listener.problem)
        self.notified.assert_called()

    def test_the_problem_clears_once_polling_works_again(self):
        FakeBotApi.statuses = [(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})]
        self.listener.listen(("123:SECRET", self.url))
        self.assertTrue(self.wait_for(lambda: self.listener.problem))
        self.assertTrue(self.wait_for(lambda: not self.listener.problem))

    def test_one_conflict_is_not_worth_reporting(self):
        with mock.patch("todolite.bot.CONFLICT_RETRY", 0.05):
            FakeBotApi.statuses = [(409, {"ok": False, "error_code": 409, "description": "Conflict"})]
            self.listener.listen(("123:SECRET", self.url))
            self.assertTrue(self.wait_for(lambda: len(FakeBotApi.polls) >= 2))
        self.assertEqual(self.listener.problem, "")

    def test_repeated_conflicts_are_reported(self):
        conflict = (409, {"ok": False, "error_code": 409, "description": "Conflict"})
        with mock.patch("todolite.bot.CONFLICT_RETRY", 0.05):
            FakeBotApi.statuses = [conflict] * 3
            self.listener.listen(("123:SECRET", self.url))
            self.assertTrue(self.wait_for(lambda: self.listener.problem))
        self.assertIn("webhook", self.listener.problem)

    def test_a_failing_reader_backs_off_instead_of_spinning(self):
        self.inbox_result = False
        self.message("Mua sữa")
        with mock.patch.object(listener, "RETRY_DELAY", 0.1), mock.patch.object(listener, "MAX_RETRY_DELAY", 0.1):
            self.listener.listen(("123:SECRET", self.url))
            time.sleep(0.35)
        self.assertLessEqual(len(self.reads), 5)

    def test_the_agent_hears_before_every_poll_so_it_can_trim_later(self):
        def poll():
            self.events.append("poll")
            if self.events.count("poll") >= 3:
                self.listener.target = None
            return False

        with mock.patch.object(Bot, "wait_for_update", side_effect=poll):
            self.listener.listen(("123:SECRET", self.url))
            self.assertTrue(self.wait_for(lambda: self.events.count("poll") >= 3))
        self.assertEqual(self.events[:6], ["chờ", "poll"] * 3)

    def test_the_reader_is_skipped_when_the_bot_changed_meanwhile(self):
        self.message("Mua sữa")
        self.listener.target = ("khac", self.url)
        target = ("123:SECRET", self.url)
        with mock.patch.object(Bot, "wait_for_update", side_effect=lambda: setattr(self.listener, "target", None) or True):
            self.listener.target = target
            self.listener.listen(("123:SECRET", self.url))
            self.assertTrue(self.wait_for(lambda: self.listener.target is None))
            time.sleep(0.1)
        self.assertEqual(self.reads, [])


if __name__ == "__main__":
    unittest.main()
