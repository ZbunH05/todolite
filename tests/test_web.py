import json
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from todolite import web
from todolite.web import post, quote, split_url


class Echo(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/slow":
            time.sleep(9)
        if self.path == "/pieces":
            self.send_response(200)
            self.send_header("Connection", "close")
            self.end_headers()
            for piece in (b"mot\n", b"hai\nb", b"a"):
                self.wfile.write(piece)
                self.wfile.flush()
                time.sleep(0.2)
            self.close_connection = True
            return
        if self.path == "/big":
            raw = bytes(range(256)) * 40000
        else:
            raw = json.dumps({"path": self.path, "body": body.decode("utf-8"), "type": self.headers.get("Content-Type"),
                              "key": self.headers.get("Authorization")}).encode("utf-8")
        self.send_response(418 if self.path == "/teapot" else 200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        pass


class QuietServer(ThreadingHTTPServer):
    def handle_error(self, *_details):
        pass  # khách bỏ đi giữa chừng là chuyện test cố ý gây ra


class Transport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = QuietServer(("127.0.0.1", 0), Echo)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def call(self, path, data=b"{}", headers="Content-Type: application/json", timeout=5):
        return post(f"{self.url}{path}", data, headers, timeout)

    def test_post_sends_the_body_and_headers(self):
        with self.call("/a/b?x=1", "chữ Việt".encode("utf-8")) as response:
            self.assertEqual(response.status, 200)
            body = json.loads(response.read())
        self.assertEqual(body, {"path": "/a/b?x=1", "body": "chữ Việt", "type": "application/json", "key": None})

    def test_several_headers(self):
        with self.call("/", headers="Content-Type: text/plain\r\nAuthorization: Bearer abc") as response:
            body = json.loads(response.read())
        self.assertEqual((body["type"], body["key"]), ("text/plain", "Bearer abc"))

    def test_error_statuses_are_readable_not_raised(self):
        with self.call("/teapot") as response:
            self.assertEqual(response.status, 418)
            self.assertEqual(json.loads(response.read())["path"], "/teapot")

    def test_a_large_body_arrives_whole(self):
        with self.call("/big") as response:
            self.assertEqual(response.read(), bytes(range(256)) * 40000)

    def test_lines_arrive_as_they_are_sent(self):
        arrivals = []
        with self.call("/pieces") as response:
            for line in response:
                arrivals.append((line, time.monotonic()))
        self.assertEqual([line for line, _ in arrivals], [b"mot", b"hai", b"ba"])
        self.assertGreater(arrivals[1][1] - arrivals[0][1], 0.1)  # không đợi hết phản hồi mới trả về

    def test_a_slow_server_times_out(self):
        with self.assertRaises(TimeoutError):  # WinHTTP làm tròn thời gian chờ lên, sai số tới 4 giây
            with self.call("/slow", timeout=1) as response:
                response.read()

    def test_a_closed_port_fails_cleanly(self):
        with self.assertRaises(OSError):
            post("http://127.0.0.1:9/", b"{}", "Content-Type: text/plain", 2)

    def test_threads_can_call_at_the_same_time(self):
        results = []

        def work(index):
            with self.call(f"/{index}") as response:
                results.append(json.loads(response.read())["path"])

        threads = [threading.Thread(target=work, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(results, [f"/{index}" for index in range(8)])

    def test_closing_twice_is_harmless(self):
        response = self.call("/")
        response.close()
        response.close()


class Urls(unittest.TestCase):
    def test_default_ports(self):
        self.assertEqual(split_url("https://api.telegram.org/bot1/getMe"), ("https", "api.telegram.org", 443, "/bot1/getMe"))
        self.assertEqual(split_url("http://localhost"), ("http", "localhost", 80, "/"))

    def test_explicit_port_and_query(self):
        self.assertEqual(split_url("https://Tele.Example.com:8443/proxy?x=1"), ("https", "tele.example.com", 8443, "/proxy?x=1"))

    def test_ipv6(self):
        self.assertEqual(split_url("http://[::1]:8081/x"), ("http", "::1", 8081, "/x"))
        self.assertEqual(split_url("http://[::1]/x"), ("http", "::1", 80, "/x"))

    def test_bad_urls(self):
        for url in ("", "https://", "https://:443", "https://a:b", "https://a:99999", "https://[::1", "https://u@host", "https://a b/c"):
            with self.assertRaises(ValueError, msg=url):
                split_url(url)

    def test_quote_keeps_a_normal_token(self):
        self.assertEqual(quote("123456:ABC-def_x"), "123456:ABC-def_x")

    def test_quote_escapes_the_rest(self):
        self.assertEqual(quote("12 3/é"), "12%203%2F%C3%A9")


class Footprint(unittest.TestCase):
    def test_network_code_does_not_pull_in_openssl_or_urllib(self):
        code = ("import sys; import todolite.bot, todolite.web; "
                "print(sorted(set(sys.modules) & {'ssl', '_ssl', 'urllib', 'urllib.request', 'http.client', 'email', 'json', 're'}))")
        output = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, check=True).stdout
        self.assertEqual(output.strip(), "[]")

    def test_read_json_loads_json_on_demand(self):
        self.assertEqual(web.read_json(b'{"ok": true}'), {"ok": True})


if __name__ == "__main__":
    unittest.main()
