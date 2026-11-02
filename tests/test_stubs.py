"""Bản rút gọn thay darkdetect và packaging cho CustomTkinter: chỉ cần đúng những phép so mà nó dùng."""
import sys
import unittest

from todolite import ui


class VersionStub(unittest.TestCase):
    def test_python_and_tk_comparisons_customtkinter_makes(self):
        parse = ui._version
        self.assertFalse(parse("3.15.2") < parse("3.10"))
        self.assertFalse(parse("3.11.17") < parse("3.10"))
        self.assertTrue(parse("3.9.18") < parse("3.10"))
        self.assertTrue(parse("9.0.4") >= parse("8.6.9"))
        self.assertTrue(parse("8.6.15") >= parse("8.6.9"))

    def test_pre_release_suffix_is_dropped(self):
        self.assertEqual(ui._version("3.16.0a1"), (3, 16))

    def test_the_stub_is_what_customtkinter_imports(self):
        if getattr(sys.modules["packaging"], "__file__", None):
            self.skipTest("packaging thật đã được nạp trước todolite.ui")
        from packaging import version
        self.assertIs(version.parse, ui._version)


if __name__ == "__main__":
    unittest.main()
