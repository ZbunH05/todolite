import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from todolite import telegram, vault
from todolite.db import Store
from todolite.schedule import to_text
from todolite.telegram import Bot, build_brief, send_scheduled
from todolite.web import ApiError, check_api_url, read_json

NOW = datetime(2026, 11, 1, 7, 30)  # Chủ Nhật, 23/9 năm Bính Ngọ


class FakeTelegram(BaseHTTPRequestHandler):
    """Máy chủ giả có cùng giao thức với api.telegram.org, chạy cục bộ."""
    replies = []
    received = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        FakeTelegram.received.append((self.path, json.loads(self.rfile.read(length) or b"{}")))
        status, body = FakeTelegram.replies.pop(0) if FakeTelegram.replies else (200, {"ok": True, "result": {"message_id": 1}})
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        pass


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeTelegram)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeTelegram.replies = []
        FakeTelegram.received = []
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = Store(os.path.join(self.folder.name, "todo.db"))
        self.store.set_secret("telegram_token", "123:SECRET")
        self.store.set_setting("telegram_chat_id", "42")
        self.store.set_setting("telegram_api_url", self.url)

    def tearDown(self):
        self.store.close()
        self.folder.cleanup()

    def bot(self):
        return Bot("123:SECRET", self.url)


class Vault(unittest.TestCase):
    def test_round_trip_with_unicode(self):
        self.assertEqual(vault.unprotect(vault.protect("token bí mật ✓")), "token bí mật ✓")

    def test_ciphertext_differs_from_input(self):
        self.assertNotIn("token", vault.protect("token"))

    def test_broken_data_gives_empty_text(self):
        self.assertEqual(vault.unprotect("không phải base64"), "")
        self.assertEqual(vault.unprotect("AAAA"), "")


class Urls(unittest.TestCase):
    def test_https_and_trailing_slash(self):
        self.assertEqual(check_api_url(" https://api.telegram.org/ "), "https://api.telegram.org")

    def test_custom_server(self):
        self.assertEqual(check_api_url("https://tele.example.com/proxy"), "https://tele.example.com/proxy")

    def test_plain_http_is_only_for_this_machine(self):
        self.assertEqual(check_api_url("http://127.0.0.1:8081"), "http://127.0.0.1:8081")
        self.assertEqual(check_api_url("http://localhost:8081"), "http://localhost:8081")
        with self.assertRaises(ApiError):
            check_api_url("http://api.telegram.org")

    def test_nonsense(self):
        for value in ("", "telegram", "ftp://x.org", "https://", "https://[::1"):
            with self.assertRaises(ApiError, msg=value):
                check_api_url(value)

    def test_missing_token(self):
        with self.assertRaises(ApiError):
            Bot("")

    def test_odd_characters_in_a_token_stay_out_of_the_url_syntax(self):
        self.assertTrue(Bot("12 3\nxin chào:AB", "https://api.telegram.org").base.endswith("/bot12%203%0Axin%20ch%C3%A0o:AB"))

    def test_html_error_pages_read_as_empty(self):
        self.assertEqual(read_json(b"<html>Bad Gateway</html>"), {})
        self.assertEqual(read_json(b"[1, 2]"), {})


class Brief(ServerCase):
    def add(self, title, due, **fields):
        return self.store.add_task(title, due_at=due, remind="", **fields)

    def text(self):
        return build_brief(self.store, NOW)

    def test_opens_with_the_royal_address_and_the_lunar_date(self):
        text = self.text()
        self.assertTrue(text.startswith("<b>Tâu hoàng thượng,</b>"))
        self.assertIn("Chủ Nhật, 01/11/2026, nhằm ngày 23 tháng 9 năm Bính Ngọ", text)
        self.assertIn("Ngày Kỷ Mão", text)

    def test_one_deadline_reads_like_the_example(self):
        self.add("Nộp đề án", "2026-11-01 23:59", all_day=1)
        self.assertIn("Hôm nay hoàng thượng có deadline <b>nộp đề án</b>.", self.text())

    def test_one_deadline_with_a_time(self):
        self.add("Nộp đề án", "2026-11-01 14:00")
        self.assertIn("có deadline <b>nộp đề án</b> lúc 14:00.", self.text())

    def test_several_deadlines_become_a_list(self):
        self.add("Nộp đề án", "2026-11-01 14:00")
        self.add("Họp nhóm", "2026-11-01 16:00")
        text = self.text()
        self.assertIn("Hôm nay hoàng thượng có 2 deadline:", text)
        self.assertIn("• <b>nộp đề án</b> lúc 14:00", text)
        self.assertIn("• <b>họp nhóm</b> lúc 16:00", text)

    def test_empty_day(self):
        self.assertIn("Hôm nay hoàng thượng không có deadline nào.", self.text())

    def test_overdue_uses_the_royal_voice(self):
        self.add("Gửi hợp đồng", "2026-10-30 07:30")
        text = self.text()
        self.assertIn("Thần xin nhắc, 1 việc đã quá hạn còn chờ hoàng thượng định đoạt:", text)
        self.assertIn("gửi hợp đồng (trễ 2 ngày)", text)

    def test_upcoming_section_lists_next_deadlines(self):
        self.add("Nộp đề án", "2026-11-13 23:59", all_day=1)
        self.assertIn("• 13/11: nộp đề án (còn 12 ngày)", self.text())

    def test_tomorrow_needs_no_countdown(self):
        self.add("Họp nhóm", "2026-11-02 09:00")
        self.assertIn("• Ngày mai lúc 09:00: họp nhóm\n", self.text())

    def test_upcoming_lists_the_nearest_first(self):
        for title, due in (("Xa", "2026-12-20 09:00"), ("Rất xa", "2027-01-20 09:00"), ("Gần", "2026-11-05 09:00"), ("Sau", "2026-11-20 09:00")):
            self.add(title, due)
        text = self.text()
        self.assertLess(text.index("gần"), text.index("sau"))
        self.assertLess(text.index("sau"), text.index("xa"))
        self.assertNotIn("rất xa", text)

    def test_time_blocks_for_today(self):
        task = self.add("Viết chương 3", None)
        self.store.update_task(task, block_start="2026-11-01 14:00", block_minutes=50)
        self.assertIn("14:00–14:50 viết chương 3", self.text())

    def test_festival_is_mentioned(self):
        text = build_brief(self.store, datetime(2026, 9, 2, 7, 30))
        self.assertIn("Hôm nay là Ngày Quốc khánh", text)

    def test_html_in_titles_is_escaped(self):
        self.add("Sửa <b>lỗi</b> & test", "2026-11-01 23:59", all_day=1)
        self.assertIn("sửa &lt;b&gt;lỗi&lt;/b&gt; &amp; test", self.text())

    def test_acronyms_and_names_keep_their_capitals(self):
        self.add("API cho đề án", "2026-11-01 23:59", all_day=1)
        self.add("Hà Nội mùa thu", "2026-11-01 23:59", all_day=1)
        text = self.text()
        self.assertIn("<b>API cho đề án</b>", text)
        self.assertIn("<b>Hà Nội mùa thu</b>", text)

    def test_one_letter_title(self):
        self.add("A", "2026-11-01 23:59", all_day=1)
        self.assertIn("<b>a</b>", self.text())

    def test_long_lists_are_capped(self):
        for index in range(25):
            self.add(f"Việc {index}", "2026-11-01 23:59", all_day=1)
        text = self.text()
        self.assertIn(f"• và {25 - telegram.MAX_LIST_ITEMS} việc khác", text)
        self.assertLess(len(text), telegram.MESSAGE_LIMIT)

    def fill_every_section(self, title):
        for index in range(25):
            self.add(f"{index} {title}", "2026-11-01 23:59", all_day=1)
            self.add(f"Trễ {index} {title}", "2026-10-20 09:00")
            self.add(f"Sau {index} {title}", "2026-11-20 09:00")
            task = self.add(f"Khối {index} {title}", None)
            self.store.update_task(task, block_start=f"2026-11-01 {index % 24:02d}:00", block_minutes=30)

    def test_long_titles_stay_within_the_message_limit(self):
        self.fill_every_section("chữ " * 400)
        self.assertLess(len(self.text()), telegram.MESSAGE_LIMIT)

    def test_emoji_titles_cannot_break_the_limit_or_the_markup(self):
        self.fill_every_section("😀" * 100)
        text = self.text()
        self.assertLessEqual(len(text.encode("utf-16-le")) // 2, telegram.MESSAGE_LIMIT)
        self.assertEqual(text.count("<b>"), text.count("</b>"))


class Calls(ServerCase):
    def test_send_goes_to_the_right_method(self):
        self.bot().send("42", "<b>Tâu</b>")
        path, body = FakeTelegram.received[0]
        self.assertEqual(path, "/bot123:SECRET/sendMessage")
        self.assertEqual(body, {"chat_id": "42", "text": "<b>Tâu</b>", "parse_mode": "HTML"})

    def test_me(self):
        FakeTelegram.replies = [(200, {"ok": True, "result": {"username": "than_bot"}})]
        self.assertEqual(self.bot().me(), "@than_bot")

    def test_latest_chat(self):
        updates = [{"update_id": 1, "message": {"chat": {"id": 11, "first_name": "Cũ"}}},
                   {"update_id": 2, "message": {"chat": {"id": 42, "first_name": "Hoàng thượng"}}}]
        FakeTelegram.replies = [(200, {"ok": True, "result": updates})]
        self.assertEqual(self.bot().latest_chat(), ("42", "Hoàng thượng"))

    def test_latest_chat_with_no_messages(self):
        FakeTelegram.replies = [(200, {"ok": True, "result": []})]
        self.assertIsNone(self.bot().latest_chat())

    def error(self, status, description):
        FakeTelegram.replies = [(status, {"ok": False, "error_code": status, "description": description})]
        with self.assertRaises(ApiError) as caught:
            self.bot().send("42", "x")
        return caught.exception

    def test_bad_token(self):
        problem = self.error(401, "Unauthorized")
        self.assertTrue(problem.permanent)
        self.assertIn("Bot Token", str(problem))

    def test_bad_chat(self):
        problem = self.error(400, "Bad Request: chat not found")
        self.assertTrue(problem.permanent)
        self.assertIn("Chat ID", str(problem))

    def test_blocked(self):
        self.assertTrue(self.error(403, "Forbidden: bot was blocked by the user").permanent)

    def test_rate_limit_and_server_errors_are_retried(self):
        self.assertFalse(self.error(429, "Too Many Requests").permanent)
        self.assertFalse(self.error(502, "Bad Gateway").permanent)

    def test_flood_control_says_how_long_to_wait(self):
        FakeTelegram.replies = [(429, {"ok": False, "error_code": 429, "description": "Too Many Requests", "parameters": {"retry_after": 37}})]
        with self.assertRaises(ApiError) as caught:
            self.bot().send("42", "x")
        self.assertEqual(caught.exception.retry_after, 37)

    def test_a_failure_inside_a_success_status(self):
        FakeTelegram.replies = [(200, {"ok": False, "error_code": 403, "description": "Forbidden"})]
        with self.assertRaises(ApiError) as caught:
            self.bot().send("42", "x")
        self.assertTrue(caught.exception.permanent)

    def test_a_login_page_on_public_wifi_is_only_a_network_problem(self):
        FakeTelegram.replies = [(200, [])]
        with self.assertRaises(ApiError) as caught:
            self.bot().send("42", "x")
        self.assertFalse(caught.exception.permanent)

    def test_malformed_token_gets_a_clear_message(self):
        problem = self.error(404, "Not Found")
        self.assertTrue(problem.permanent)
        self.assertIn("Bot Token", str(problem))

    def test_no_connection(self):
        with self.assertRaises(ApiError) as caught:
            Bot("123:SECRET", "http://127.0.0.1:9").send("42", "x")
        self.assertFalse(caught.exception.permanent)

    def test_errors_never_contain_the_token(self):
        for call in (lambda: Bot("123:SECRET", "http://127.0.0.1:9").send("42", "x"), lambda: self.error(401, "Unauthorized")):
            try:
                call()
            except ApiError as error:
                self.assertNotIn("SECRET", str(error))


class Scheduled(ServerCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(telegram, "log")  # lỗi giả không được ghi vào app.log thật
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_it(self):
        waits = []
        result = send_scheduled(self.store, NOW, wait=waits.append)
        return result, waits

    def test_success_is_remembered(self):
        self.assertEqual(self.run_it(), (True, []))
        self.assertEqual(self.store.setting("telegram_last_sent"), "2026-11-01")
        self.assertIn("Đã gửi", self.store.setting("telegram_status"))

    def test_second_run_on_the_same_day_sends_nothing(self):
        self.run_it()
        self.run_it()
        self.assertEqual(len(FakeTelegram.received), 1)

    def test_network_hiccup_is_retried(self):
        FakeTelegram.replies = [(502, {"ok": False, "error_code": 502, "description": "Bad Gateway"})]
        result, waits = self.run_it()
        self.assertTrue(result)
        self.assertEqual(waits, [telegram.RETRY_DELAY])

    def test_flood_control_wait_is_respected_but_bounded(self):
        for seconds, expected in ((40, 40), (9999, telegram.MAX_RETRY_DELAY), (1, telegram.RETRY_DELAY)):
            self.store.set_setting("telegram_last_sent", "")
            FakeTelegram.replies = [(429, {"ok": False, "error_code": 429, "description": "x", "parameters": {"retry_after": seconds}})]
            self.assertEqual(self.run_it(), (True, [expected]))

    def test_gives_up_for_now_after_all_attempts(self):
        failure = (502, {"ok": False, "error_code": 502, "description": "Bad Gateway"})
        FakeTelegram.replies = [failure] * telegram.SEND_ATTEMPTS
        result, waits = self.run_it()
        self.assertFalse(result)
        self.assertEqual(len(waits), telegram.SEND_ATTEMPTS - 1)
        self.assertEqual(self.store.setting("telegram_last_sent"), "")
        self.assertEqual(self.store.setting("telegram_failed_on"), "")
        self.assertIn("thử lại", self.store.setting("telegram_status"))

    def test_bad_token_stops_for_the_day(self):
        FakeTelegram.replies = [(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})]
        result, waits = self.run_it()
        self.assertEqual((result, waits), (False, []))
        self.assertEqual(self.store.setting("telegram_failed_on"), "2026-11-01")
        self.assertIn("Bot Token", self.store.setting("telegram_status"))

    def test_token_is_never_written_to_the_status(self):
        FakeTelegram.replies = [(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})]
        self.run_it()
        self.assertNotIn("SECRET", self.store.setting("telegram_status"))

    def test_uses_the_real_tasks(self):
        self.store.add_task("Nộp đề án", due_at=to_text(NOW + timedelta(hours=3)), remind="")
        self.run_it()
        self.assertIn("nộp đề án", FakeTelegram.received[0][1]["text"])


if __name__ == "__main__":
    unittest.main()
