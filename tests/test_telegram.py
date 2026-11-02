import json
import os
import tempfile
import threading
import unittest
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from todolite import lunar, telegram, vault
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

    def text(self, now=NOW):
        return build_brief(self.store, now)

    def section(self, title, now=NOW):
        """Một phần của tờ tấu, tính từ tiêu đề in đậm tới dòng trống kế tiếp."""
        return next(part for part in self.text(now).split("\n\n") if part.startswith(f"<b>{title}</b>"))


class Structure(Brief):
    def test_five_parts_in_the_requested_order(self):
        self.add("Nộp đề án", "2026-11-01 14:00")
        text = self.text()
        marks = ("<b>Muôn tâu Bệ hạ,</b>", "<b>Báo cáo ngày</b>", "<b>Hạn định</b>", "<b>Thuận thiên, kiêng kỵ</b>", "Thần xin cáo lui")
        self.assertEqual([text.index(mark) for mark in marks], sorted(text.index(mark) for mark in marks))
        self.assertTrue(text.startswith(marks[0]))
        self.assertEqual(len(text.split("\n\n")), 5)

    def test_first_line_can_be_read_from_the_phone_notification(self):
        self.add("Nộp đề án", "2026-11-01 14:00")
        self.add("Gửi hợp đồng", "2026-10-30 07:30")
        self.assertEqual(self.text().split("\n")[0], "<b>Muôn tâu Bệ hạ,</b> hôm nay có 1 việc đến hạn, 1 việc đã trễ.")

    def test_addresses_the_emperor_only_as_be_ha(self):
        self.add("Gửi hợp đồng", "2026-10-30 07:30")
        self.assertNotIn("hoàng thượng", self.text().lower())

    def test_day_report(self):
        part = self.section("Báo cáo ngày")
        self.assertIn("Chủ Nhật, 01/11/2026, tức 23 tháng 9 năm Bính Ngọ.", part)
        self.assertIn("Ngày Kỷ Mão, tháng Mậu Tuất, tiết Sương giáng.", part)
        self.assertIn("hôm nay là <b>ngày xấu</b>: hắc đạo Câu Trần, trực Chấp, sao Mão xấu, phạm", part)

    def test_festival_is_reported(self):
        self.assertIn("Hôm nay là Ngày Quốc khánh", self.section("Báo cáo ngày", datetime(2026, 9, 2, 7, 30)))

    def test_closing_wishes_health_and_peace(self):
        tail = self.text().split("\n\n")[-1]
        self.assertIn("quốc thái dân an", tail)
        self.assertTrue(tail.endswith("!"))
        self.assertTrue(any(tail.endswith(sign) for sign in telegram.SIGN_OFFS))


class Deadlines(Brief):
    def test_one_deadline_today(self):
        self.add("Nộp đề án", "2026-11-01 23:59", all_day=1)
        self.assertIn("Hôm nay (1 việc):\n• <b>Nộp đề án</b>", self.section("Hạn định"))

    def test_deadline_with_a_time(self):
        self.add("Nộp đề án", "2026-11-01 14:00")
        self.assertIn("• <b>Nộp đề án</b> lúc 14:00", self.section("Hạn định"))

    def test_empty_day(self):
        part = self.section("Hạn định")
        self.assertIn("Hôm nay không có việc đến hạn.", part)
        self.assertIn("14 ngày tới chưa có hạn nào.", part)

    def test_overdue_comes_first(self):
        self.add("Gửi hợp đồng", "2026-10-30 07:30")
        self.add("Nộp đề án", "2026-11-01 14:00")
        part = self.section("Hạn định")
        self.assertIn("Đã trễ (1 việc):\n• Gửi hợp đồng (trễ 2 ngày)", part)
        self.assertLess(part.index("Đã trễ"), part.index("Hôm nay ("))

    def test_short_delays_show_hours(self):
        self.add("Gửi hợp đồng", "2026-11-01 05:00")
        self.assertIn("(trễ 2 giờ 30 phút)", self.section("Hạn định"))

    def test_long_delays_show_days_only(self):
        self.add("Gửi hợp đồng", "2026-10-29 05:00")
        self.assertIn("(trễ 3 ngày)", self.section("Hạn định"))

    def test_next_fourteen_days_are_listed_with_the_time_left(self):
        self.add("Nộp đề án", "2026-11-13 23:59", all_day=1)
        self.assertIn("14 ngày tới (1 việc):\n• T6 13/11, còn 12 ngày: Nộp đề án", self.section("Hạn định"))

    def test_tomorrow_needs_no_countdown(self):
        self.add("Họp nhóm", "2026-11-02 09:00")
        self.assertIn("• Ngày mai lúc 09:00: Họp nhóm", self.section("Hạn định"))

    def test_window_ends_after_fourteen_days(self):
        self.add("Vừa đủ", "2026-11-15 23:59", all_day=1)
        self.add("Quá xa", "2026-11-16 00:00")
        part = self.section("Hạn định")
        self.assertIn("Vừa đủ", part)
        self.assertNotIn("Quá xa", part)

    def test_nearest_comes_first(self):
        for title, due in (("Sau", "2026-11-10 09:00"), ("Gần", "2026-11-05 09:00")):
            self.add(title, due)
        part = self.section("Hạn định")
        self.assertLess(part.index("Gần"), part.index("Sau"))

    def test_time_blocks_for_today(self):
        task = self.add("Viết chương 3", None)
        self.store.update_task(task, block_start="2026-11-01 14:00", block_minutes=50)
        self.assertIn("Khối giờ đã định:\n• 14:00–14:50 Viết chương 3", self.section("Hạn định"))

    def test_daily_habits_are_not_deadlines(self):
        self.add("Uống đủ 2 lít nước", "2026-10-30 23:59", all_day=1, recur="daily")
        self.add("Đi bộ", "2026-11-02 06:00", recur="weekdays")
        text = self.text()
        self.assertTrue(text.startswith("<b>Muôn tâu Bệ hạ,</b> hôm nay không có việc đến hạn."))
        self.assertIn("Việc thường nhật: uống đủ 2 lít nước.", text)
        self.assertNotIn("Đã trễ", text)
        self.assertNotIn("Đi bộ", text)

    def test_weekly_and_monthly_repeats_stay_deadlines(self):
        self.add("Đóng tiền điện", "2026-11-05 23:59", all_day=1, recur="monthly")
        self.assertIn("Đóng tiền điện", self.section("Hạn định"))

    def test_html_in_titles_is_escaped(self):
        self.add("Sửa <b>lỗi</b> & test", "2026-11-01 23:59", all_day=1)
        self.assertIn("Sửa &lt;b&gt;lỗi&lt;/b&gt; &amp; test", self.text())

    def test_long_lists_are_capped(self):
        for index in range(25):
            self.add(f"Việc {index}", "2026-11-01 23:59", all_day=1)
            self.add(f"Trễ {index}", "2026-10-20 09:00")
        text = self.text()
        self.assertIn(f"• và {25 - telegram.MAX_LIST_ITEMS} việc khác", text)
        self.assertIn(f"• và {25 - telegram.MAX_LATE_ITEMS} việc khác", text)
        self.assertLess(len(text), telegram.MESSAGE_LIMIT)


class Context(Brief):
    def test_quiet_day_praises_the_emperor(self):
        tones = {telegram._pick(telegram.CALM_TONES, NOW.date() + timedelta(days=n)) for n in range(3)}
        self.assertEqual(tones, set(telegram.CALM_TONES))
        self.assertIn(telegram._pick(telegram.CALM_TONES, NOW.date()), self.text())

    def test_overdue_turns_to_remonstrance(self):
        self.add("Gửi hợp đồng", "2026-10-30 07:30")
        self.assertIn(telegram._pick(telegram.LATE_TONES, NOW.date()).format(session="sớm nay"), self.text())

    def test_many_overdue_risks_his_neck(self):
        for index in range(telegram.HEAVY_LATE):
            self.add(f"Trễ {index}", "2026-10-20 09:00")
        self.assertIn("thà chịu búa rìu phủ việt", self.text())

    def test_today_sounds_like_an_urgent_dispatch(self):
        self.add("Nộp đề án", "2026-11-01 14:00")
        self.assertIn(telegram._pick(telegram.URGENT_TONES, NOW.date()).format(session="sớm nay"), self.text())

    def test_a_near_deadline_is_announced_ahead(self):
        self.add("Nộp đề án", "2026-11-03 09:00")
        self.assertIn("hạn kế tiếp chỉ còn 2 ngày", self.text())

    def test_a_far_deadline_keeps_the_peace(self):
        self.add("Nộp đề án", "2026-11-10 09:00")
        self.assertNotIn("hạn kế tiếp", self.text())

    def test_session_follows_the_real_hour(self):
        self.add("Nộp đề án", "2026-11-01 23:00")
        self.assertIn("tờ tấu tối nay", self.text(datetime(2026, 11, 1, 20, 15)))
        self.assertIn("tờ tấu chiều nay", self.text(datetime(2026, 11, 1, 15, 0)))

    def test_festival_opening(self):
        self.assertIn("Nhân dịp Ngày Quốc khánh, thần cúi lạy dưới đan trì", self.text(datetime(2026, 9, 2, 7, 30)))

    def test_birthday_by_the_solar_date(self):
        self.store.set_setting("birth_date", "1999-11-01")
        text = self.text()
        self.assertIn("Vạn thọ thánh tiết", text)
        self.assertIn(telegram.BIRTHDAY_WISH, text)

    def test_birthday_by_the_lunar_date(self):
        self.store.set_setting("birth_date", "1999-11-01")
        born = lunar.solar_to_lunar(date(1999, 11, 1))
        day = lunar.lunar_to_solar(born.day, born.month, 2027)
        self.assertNotEqual((day.month, day.day), (11, 1))
        self.assertIn("Vạn thọ thánh tiết", self.text(datetime(day.year, day.month, day.day, 7, 30)))

    def test_no_birthday_on_other_days(self):
        self.store.set_setting("birth_date", "1999-11-02")
        self.assertNotIn("Vạn thọ", self.text())

    def test_wording_changes_from_day_to_day(self):
        self.assertGreater(len({self.text(NOW + timedelta(days=n)).split("\n")[-1] for n in range(6)}), 1)


class Advice(Brief):
    GOOD_DAY = datetime(2026, 11, 7, 7, 30)  # trực Khai
    BAD_DAY = datetime(2026, 11, 18, 7, 30)  # phạm Thụ Tử

    def test_lists_what_to_do_and_avoid(self):
        part = self.section("Thuận thiên, kiêng kỵ", self.GOOD_DAY)
        self.assertRegex(part, r"Việc thuận thiên: .+\.")
        self.assertRegex(part, r"Việc kiêng kỵ: .+\.")
        self.assertIn("Giờ hoàng đạo: Tý 23–1h, ", part)

    def test_long_lists_are_shortened(self):
        part = self.section("Thuận thiên, kiêng kỵ", datetime(2026, 11, 26, 7, 30))
        self.assertRegex(part, r"Việc kiêng kỵ: .+ và \d+ việc khác\.")

    def test_a_feared_day_advises_nothing_new(self):
        part = self.section("Thuận thiên, kiêng kỵ", self.BAD_DAY)
        self.assertIn("Hôm nay không có việc nên khởi sự", part)
        self.assertIn("Việc kiêng kỵ: mọi việc lớn", part)

    def test_task_on_a_forbidden_day_is_flagged_with_a_better_day(self):
        self.add("Ký hợp đồng thuê nhà", "2026-11-18 09:00")
        text = self.text(self.BAD_DAY)
        self.assertIn("• <b>Ký hợp đồng thuê nhà</b> hôm nay phạm Thụ Tử, kiêng mọi việc lớn.", text)
        self.assertRegex(text, r"Ngày gần nhất không vướng là T\d \d\d/11\.")
        self.assertIn("định đoạt: 1 việc vướng điều kiêng có đổi ngày hay không.", text)

    def test_upcoming_task_is_flagged_early(self):
        self.add("Lễ cưới", "2026-11-02 09:00")  # ngày mai là trực Phá
        self.assertRegex(self.text(), r"<b>Lễ cưới</b> ngày 02/11 phạm .+, kiêng cưới hỏi\.")

    def test_ordinary_tasks_raise_no_flag(self):
        self.add("Viết báo cáo", "2026-11-18 09:00")
        self.assertNotIn("Ngu ý của thần", self.text(self.BAD_DAY))

    def test_clashes_are_capped(self):
        for index in range(telegram.MAX_CLASHES + 2):
            self.add(f"Ký hợp đồng {index}", "2026-11-18 09:00")
        self.assertIn("• và 2 việc khác", self.section("Thuận thiên, kiêng kỵ", self.BAD_DAY))

    def test_age_note_uses_the_royal_address(self):
        self.store.set_setting("birth_date", "1982-06-01")  # tuổi Nhâm Tuất, ngày 2/11 là ngày Canh Thìn xung Tuất
        self.assertIn("Ngày này xung tuổi Tuất của Bệ hạ.", self.text(datetime(2026, 11, 2, 7, 30)))


class Closing(Brief):
    def test_asks_a_decision_on_late_work(self):
        self.add("Gửi hợp đồng", "2026-10-30 07:30")
        self.assertIn("Thần xin cáo lui, cúi mong Bệ hạ thánh minh định đoạt: 1 việc đã trễ nên làm ngay hay dời hạn.", self.text())

    def test_two_decisions_are_listed_together(self):
        self.add("Gửi báo cáo", "2026-10-30 07:30")
        self.add("Ký hợp đồng", "2026-11-02 09:00")
        self.assertIn("định đoạt: 1 việc đã trễ nên làm ngay hay dời hạn, 1 việc vướng điều kiêng có đổi ngày hay không.", self.text())

    def test_asks_to_handle_today(self):
        self.add("Nộp đề án", "2026-11-01 14:00")
        self.assertIn("định liệu các việc đến hạn hôm nay", self.text())

    def test_quiet_day_just_waits(self):
        self.assertIn("Thần xin cáo lui, chờ thánh ý của Bệ hạ.", self.text())


class Limits(Brief):
    def fill_every_section(self, title):
        for index in range(25):
            self.add(f"{index} {title}", "2026-11-01 23:59", all_day=1)
            self.add(f"Trễ {index} {title}", "2026-10-20 09:00")
            self.add(f"Sau {index} {title}", "2026-11-10 09:00")
            task = self.add(f"Khối {index} {title}", None)
            self.store.update_task(task, block_start=f"2026-11-01 {index % 24:02d}:00", block_minutes=30)

    def test_long_titles_stay_within_the_message_limit(self):
        self.fill_every_section("chữ " * 400)
        text = self.text()
        self.assertLess(len(text), telegram.MESSAGE_LIMIT)
        self.assertIn("quốc thái dân an", text)

    def test_emoji_titles_cannot_break_the_limit_or_the_closing(self):
        self.fill_every_section("😀" * 100)
        text = self.text()
        self.assertLessEqual(len(text.encode("utf-16-le")) // 2, telegram.MESSAGE_LIMIT)
        self.assertEqual(text.count("<b>"), text.count("</b>"))
        self.assertIn("Thần xin cáo lui", text)

    def test_acronyms_and_names_keep_their_capitals_mid_sentence(self):
        self.assertEqual(telegram._mid_sentence("API cho đề án"), "API cho đề án")
        self.assertEqual(telegram._mid_sentence("Hà Nội mùa thu"), "Hà Nội mùa thu")
        self.assertEqual(telegram._mid_sentence("A"), "a")


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

    def calls(self, method):
        return [body for path, body in FakeTelegram.received if path.endswith("/" + method)]

    def test_second_run_on_the_same_day_sends_nothing(self):
        self.run_it()
        self.run_it()
        self.assertEqual(len(self.calls("sendMessage")), 1)

    def test_menu_of_commands_is_registered_once(self):
        self.run_it()
        self.store.set_setting("telegram_last_sent", "")
        self.run_it()
        menus = self.calls("setMyCommands")
        self.assertEqual(len(menus), 1)
        self.assertEqual([item["command"] for item in menus[0]["commands"]], ["rp", "today", "week", "huy", "help"])

    def test_a_failed_menu_does_not_spoil_the_brief(self):
        FakeTelegram.replies = [(200, {"ok": True, "result": {"message_id": 1}}), (400, {"ok": False, "error_code": 400, "description": "x"})]
        self.assertEqual(self.run_it(), (True, []))
        self.assertEqual(self.store.setting("telegram_commands"), "")

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
        self.assertIn("Nộp đề án", FakeTelegram.received[0][1]["text"])


if __name__ == "__main__":
    unittest.main()
