import unittest
import xml.dom.minidom

from todolite import toast


class Xml(unittest.TestCase):
    def build(self):
        return toast.build_xml("Còn 15 phút: Báo cáo <Q3> & \"tổng hợp\"", ["Hạn 14:00", "Dòng hai"])

    def test_special_characters_produce_valid_xml(self):
        document = xml.dom.minidom.parseString(self.build())
        title = document.getElementsByTagName("text")[0].firstChild.data
        self.assertEqual(title, "Còn 15 phút: Báo cáo <Q3> & \"tổng hợp\"")

    def test_all_lines_are_present(self):
        document = xml.dom.minidom.parseString(self.build())
        self.assertEqual(len(document.getElementsByTagName("text")), 3)

    def test_toast_has_no_actions(self):
        self.assertNotIn("<action", self.build())
        self.assertNotIn("launch", self.build())

    def test_logo_path_is_encoded(self):
        self.assertEqual(toast._file_uri(r"C:\Users\A\app local\Việc\app.png"),
                         "file:///C:/Users/A/app%20local/Vi%E1%BB%87c/app.png")

    def test_logo_is_embedded(self):
        self.assertIn('placement="appLogoOverride"', self.build())


if __name__ == "__main__":
    unittest.main()
