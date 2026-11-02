import ast
import os
import unittest
from unittest import mock

from todolite import popups
from todolite.paths import ROOT


class FakeStore:
    def __init__(self, scale):
        self.scale = scale

    def setting(self, key):
        return {"text_scale": self.scale}[key]


class Fonts(unittest.TestCase):
    def setUp(self):
        saved = (popups._fonts_loaded, popups.FONT_FAMILY, popups.FONT_SEMIBOLD)
        self.addCleanup(lambda: (setattr(popups, "_fonts_loaded", saved[0]), setattr(popups, "FONT_FAMILY", saved[1]), setattr(popups, "FONT_SEMIBOLD", saved[2])))
        popups._fonts_loaded = False
        popups.FONT_FAMILY, popups.FONT_SEMIBOLD = "Segoe UI Variable Text", "Segoe UI Variable Text Semibold"

    def test_bundled_font_is_used_when_it_loads(self):
        with mock.patch.object(popups, "load_private_fonts", return_value=True):
            popups._load_fonts()
        self.assertEqual((popups.FONT_FAMILY, popups.FONT_SEMIBOLD), ("Be Vietnam Pro", "Be Vietnam Pro SemiBold"))

    def test_falls_back_to_windows_fonts(self):
        with mock.patch.object(popups, "load_private_fonts", return_value=False):
            popups._load_fonts()
        self.assertEqual(popups.FONT_FAMILY, "Segoe UI Variable Text")

    def test_fonts_load_only_once(self):
        with mock.patch.object(popups, "load_private_fonts", return_value=True) as loader:
            popups._load_fonts()
            popups._load_fonts()
        self.assertEqual(loader.call_count, 1)

    def test_a_missing_font_file_does_not_break_a_popup(self):
        with mock.patch.object(popups, "FONT_PATHS", (os.path.join(ROOT, "assets", "fonts", "khong-co.ttf"),)):
            popups._load_fonts()
        self.assertEqual(popups.FONT_FAMILY, "Segoe UI Variable Text")

    def test_font_files_exist(self):
        for path in popups.FONT_PATHS:
            self.assertTrue(os.path.isfile(path), path)

    def test_nothing_loads_before_a_popup_is_made(self):
        with open(popups.__file__, encoding="utf-8") as stream:
            tree = ast.parse(stream.read())
        top_level_calls = [node for node in tree.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)]
        self.assertEqual(top_level_calls, [])


class TextScale(unittest.TestCase):
    def dpi(self, scale, screen=96):
        with mock.patch.object(popups, "GetDpiForWindow", return_value=screen), mock.patch.object(popups, "_load_fonts"):
            return popups._text_dpi(None, FakeStore(scale))

    def test_normal_size(self):
        self.assertEqual(self.dpi("1"), 96)

    def test_follows_the_setting(self):
        self.assertAlmostEqual(self.dpi("1.3"), 124.8)
        self.assertAlmostEqual(self.dpi("1.15"), 110.4)

    def test_multiplies_the_screen_dpi(self):
        self.assertAlmostEqual(self.dpi("1.3", 144), 187.2)

    def test_building_a_popup_loads_the_fonts(self):
        with mock.patch.object(popups, "GetDpiForWindow", return_value=96), mock.patch.object(popups, "_load_fonts") as loader:
            popups._text_dpi(None, FakeStore("1"))
        loader.assert_called_once()


if __name__ == "__main__":
    unittest.main()
