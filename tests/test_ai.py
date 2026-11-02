import json
import threading
import unittest
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer

from todolite import ai
from todolite.web import ApiError

DAY = date(2026, 11, 1)
BIRTH = date(1999, 1, 20)  # trước Tết Kỷ Mão: vẫn thuộc năm Mậu Dần


def chunk(content):
    return b"data: " + json.dumps({"choices": [{"delta": {"content": content}}]}).encode("utf-8") + b"\n\n"


class FakeAi(BaseHTTPRequestHandler):
    """Máy chủ giả nói cùng giao thức SSE với API kiểu OpenAI."""
    status = 200
    body = b""
    received = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        FakeAi.received = (self.path, self.headers.get("Authorization"), json.loads(self.rfile.read(length)))
        self.send_response(FakeAi.status)
        self.send_header("Content-Type", "text/event-stream" if FakeAi.status == 200 else "application/json")
        self.send_header("Content-Length", str(len(FakeAi.body)))
        self.end_headers()
        self.wfile.write(FakeAi.body)

    def log_message(self, *_args):
        pass


class Streaming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeAi)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/chat/completions"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeAi.status = 200
        FakeAi.body = b""

    def ask(self):
        return list(ai.stream_answer(self.url, "KEY-BI-MAT", "mo-hinh", ai.build_messages("Câu hỏi?", DAY)))

    def fail(self, status, body=b""):
        FakeAi.status, FakeAi.body = status, body
        with self.assertRaises(ApiError) as caught:
            self.ask()
        return str(caught.exception)

    def test_pieces_arrive_in_order(self):
        FakeAi.body = chunk("## Tổng") + chunk(" quan") + b"data: [DONE]\n\n"
        self.assertEqual(self.ask(), ["## Tổng", " quan"])

    def test_request_shape(self):
        FakeAi.body = chunk("x") + b"data: [DONE]\n\n"
        self.ask()
        path, authorization, payload = FakeAi.received
        self.assertEqual(path, "/chat/completions")
        self.assertEqual(authorization, "Bearer KEY-BI-MAT")
        self.assertEqual(payload["model"], "mo-hinh")
        self.assertIs(payload["stream"], True)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertIn("Câu hỏi người dùng: Câu hỏi?", payload["messages"][-1]["content"])

    def test_keep_alive_and_thinking_are_skipped(self):
        thinking = b"data: " + json.dumps({"choices": [{"delta": {"reasoning_content": "suy nghĩ", "content": None}}]}).encode() + b"\n\n"
        FakeAi.body = b": keep-alive\n\n" + thinking + chunk("Trả lời") + b"data: [DONE]\n\n"
        self.assertEqual(self.ask(), ["Trả lời"])

    def test_empty_stream_is_reported(self):
        FakeAi.body = b"data: [DONE]\n\n"
        self.assertIn("chưa trả về", self.fail(200, FakeAi.body))

    def test_bad_key(self):
        self.assertIn("API key", self.fail(401, b'{"error": {"message": "invalid"}}'))

    def test_out_of_balance(self):
        self.assertIn("hết số dư", self.fail(402))

    def test_wrong_model_shows_the_server_message(self):
        self.assertIn("Model Not Exist", self.fail(400, b'{"error": {"message": "Model Not Exist"}}'))

    def test_rate_limit_and_outage(self):
        self.assertIn("giới hạn", self.fail(429))
        self.assertIn("sự cố", self.fail(503))

    def test_no_connection(self):
        with self.assertRaises(ApiError) as caught:
            list(ai.stream_answer("http://127.0.0.1:9/x", "KEY-BI-MAT", "m", []))
        self.assertIn("Không kết nối", str(caught.exception))
        self.assertNotIn("KEY-BI-MAT", str(caught.exception))

    def test_plain_http_is_refused_before_sending_the_key(self):
        with self.assertRaises(ApiError):
            list(ai.stream_answer("http://api.example.com/x", "KEY-BI-MAT", "m", []))


class Prompt(unittest.TestCase):
    def test_thinking_is_turned_off_only_on_deepseek(self):
        self.assertEqual(ai.request_body("https://api.deepseek.com/chat/completions", "m", [])["thinking"], {"type": "disabled"})
        self.assertNotIn("thinking", ai.request_body("https://api.openai.com/v1/chat/completions", "m", []))

    def test_facts_cover_the_day(self):
        text = "\n".join(ai.day_facts(DAY))
        for fact in ("Chủ Nhật, 01/11/2026", "23 tháng 9", "Bính Ngọ", "Kỷ Mão", "Mậu Tuất", "Hắc đạo Câu Trần", "trực Chấp", "Việc nên kiêng", "Tý, Dần, Mão, Ngọ, Mùi, Dậu"):
            self.assertIn(fact, text)

    def test_birth_year_follows_the_lunar_calendar(self):
        self.assertIn("năm Mậu Dần, tuổi Hổ", ai.birth_text(BIRTH))
        self.assertIn("năm Kỷ Mão, tuổi Mèo", ai.birth_text(date(1999, 2, 16)))

    def test_birth_date_is_only_sent_when_given(self):
        self.assertNotIn("Ngày sinh", ai.build_messages("?", DAY)[-1]["content"])
        self.assertIn("Ngày sinh: 20/01/1999", ai.build_messages("?", DAY, BIRTH)[-1]["content"])

    def test_history_is_trimmed(self):
        history = [{"role": "user", "content": str(index)} for index in range(20)]
        messages = ai.build_messages("?", DAY, None, history)
        self.assertEqual(len(messages), ai.HISTORY_LIMIT + 2)
        self.assertEqual(messages[1]["content"], "14")


class Offline(unittest.TestCase):
    def test_sections(self):
        text = ai.offline_answer("Hôm nay thế nào?", DAY)
        for heading in ("## Tổng quan", "## Bối cảnh ngày xem", "## Lời nhắc"):
            self.assertIn(heading, text)

    def test_topic_follows_the_question(self):
        self.assertIn(ai.TOPICS[0][1], ai.offline_answer("Đường tình duyên của tôi?", DAY))
        self.assertIn(ai.TOPICS[1][1], ai.offline_answer("Công việc hiện tại ra sao?", DAY))
        self.assertIn(ai.TOPICS[2][1], ai.offline_answer("Tài chính của tôi?", DAY))
        self.assertIn(ai.GENERAL_TOPIC, ai.offline_answer("Hôm nay nên làm gì?", DAY))

    def test_day_quality(self):
        self.assertIn("Ngày xấu", ai.offline_answer("?", DAY))
        self.assertIn("Hoàng đạo", ai.offline_answer("?", date(2026, 11, 11)))

    def test_says_it_is_not_ai(self):
        self.assertIn("chưa dùng AI", ai.offline_answer("?", DAY))

    def test_birth_is_included(self):
        self.assertIn("20/01/1999", ai.offline_answer("?", DAY, BIRTH))


class Runs(unittest.TestCase):
    def test_heading_and_paragraph(self):
        self.assertEqual(ai.answer_runs("## Tổng quan\nNội dung"),
                         [("Tổng quan\n", "heading"), ("Nội dung", None), ("\n", None)])

    def test_no_blank_line_before_a_heading(self):
        self.assertEqual(ai.answer_runs("Một\n\n## Hai")[:3], [("Một", None), ("\n", None), ("Hai\n", "heading")])

    def test_bold(self):
        self.assertEqual(ai.answer_runs("a **b** c"), [("a ", None), ("b", "bold"), (" c", None), ("\n", None)])

    def test_unfinished_bold_while_streaming(self):
        self.assertEqual(ai.answer_runs("a **b"), [("a ", None), ("b", "bold"), ("\n", None)])

    def test_bullets(self):
        self.assertEqual(ai.answer_runs("- một\n* hai")[0], ("• một", None))
        self.assertEqual(ai.answer_runs("- một\n* hai")[2], ("• hai", None))

    def test_bold_marks_in_a_heading_are_dropped(self):
        self.assertEqual(ai.answer_runs("### **Điểm sáng**")[0], ("Điểm sáng\n", "heading"))


if __name__ == "__main__":
    unittest.main()
