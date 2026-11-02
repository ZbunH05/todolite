import unittest
from datetime import date, timedelta

from todolite import quotes

DAY = date(2026, 11, 3)


def cycle_start(day, length):
    return date.fromordinal(day.toordinal() - day.toordinal() % length)


class Store(unittest.TestCase):
    def test_three_hundred_quotes_in_six_topics(self):
        self.assertEqual([len(items) for *_, items in quotes.TOPICS], [50] * 6)
        self.assertEqual(len(set(quotes.TOPIC_KEYS)), 6)

    def test_every_quote_has_text_and_author(self):
        for _key, _name, _label, items in quotes.TOPICS:
            for text, author in items:
                self.assertTrue(text.strip() and author.strip(), text)
                self.assertFalse(text.startswith('"') or text.endswith('"'), text)  # app tự đặt ngoặc kép

    def test_kept_as_written(self):
        self.assertEqual(quotes.TOPICS[0][3][0], ("Uống nước nhớ nguồn.", "Khuyết danh"))
        self.assertEqual(quotes.TOPICS[5][3][-1][1], "Khuyết danh")
        self.assertEqual(quotes.TOPICS[1][3][0][1], "Khổng Tử")


class Daily(unittest.TestCase):
    def test_same_quote_all_day_in_every_process(self):
        self.assertEqual(quotes.for_day(DAY), quotes.for_day(DAY))

    def test_changes_from_day_to_day(self):
        self.assertNotEqual(quotes.for_day(DAY), quotes.for_day(DAY + timedelta(days=1)))

    def test_no_quote_repeats_within_a_round(self):
        start = cycle_start(DAY, 300)
        shown = [quotes.for_day(start + timedelta(days=offset)) for offset in range(300)]
        self.assertEqual(len(set(shown)), 300)

    def test_topics_take_turns(self):
        start = cycle_start(DAY, 300)
        topics = [quotes.for_day(start + timedelta(days=offset)).topic for offset in range(300)]
        longest = run = 1
        for previous, current in zip(topics, topics[1:]):
            run = run + 1 if current == previous else 1
            longest = max(longest, run)
        self.assertLessEqual(longest, 2)
        self.assertEqual(len(set(topics[:6])), 6)

    def test_order_looks_random(self):
        start = cycle_start(DAY, 300)
        texts = [quotes.for_day(start + timedelta(days=offset)).text for offset in range(10)]
        in_file = [text for *_, items in quotes.TOPICS for text, _ in items]
        self.assertNotEqual(sorted(texts, key=in_file.index), texts)

    def test_only_chosen_topics(self):
        chosen = ("will", "life")
        self.assertEqual({quotes.for_day(DAY + timedelta(days=offset), chosen).topic for offset in range(40)}, set(chosen))

    def test_quote_carries_its_topic_label(self):
        quote = quotes.for_day(DAY, ("east",))
        self.assertEqual((quote.topic, quote.label), ("east", "Triết lý phương Đông"))


class Setting(unittest.TestCase):
    def test_empty_means_all(self):
        self.assertEqual(quotes.chosen_topics(""), quotes.TOPIC_KEYS)

    def test_unknown_keys_are_ignored(self):
        self.assertEqual(quotes.chosen_topics("life,xyz,folk"), ("folk", "life"))
        self.assertEqual(quotes.chosen_topics("xyz"), quotes.TOPIC_KEYS)


if __name__ == "__main__":
    unittest.main()
