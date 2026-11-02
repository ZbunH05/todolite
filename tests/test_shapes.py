import unittest

from todolite.ui import shapes


class Mask(unittest.TestCase):
    def test_weights_always_sum_to_one(self):
        for width in (0, 1, 2):
            for row in shapes._mask(10, width):
                for weights in row:
                    self.assertAlmostEqual(sum(weights), 1)

    def test_outer_corner_is_background_and_inner_corner_is_fill(self):
        mask = shapes._mask(10, 1)
        self.assertEqual(mask[0][0], (1.0, 0.0, 0.0))
        self.assertEqual(mask[9][9], (0.0, 0.0, 1.0))

    def test_no_outline_means_no_ring(self):
        for row in shapes._mask(8, 0):
            for _, ring, _ in row:
                self.assertEqual(ring, 0)

    def test_outline_has_a_ring(self):
        self.assertGreater(sum(weights[1] for row in shapes._mask(10, 1) for weights in row), 5)

    def test_edge_pixels_are_blended(self):
        """Khử răng cưa: có điểm ảnh nằm giữa nền và ruột, không chỉ toàn nền hoặc toàn ruột."""
        self.assertTrue(any(0 < weights[0] < 1 for row in shapes._mask(10, 0) for weights in row))

    def test_masks_are_mirrored_across_the_diagonal(self):
        mask = shapes._mask(9, 1)
        for y in range(9):
            for x in range(9):
                self.assertEqual(mask[y][x], mask[x][y])

    def test_mask_is_cached(self):
        self.assertIs(shapes._mask(7, 1), shapes._mask(7, 1))


class Pixel(unittest.TestCase):
    BACK, RING, FILL = (0, 0, 0), (255, 0, 0), (255, 255, 255)

    def test_pure_weights_give_pure_colors(self):
        self.assertEqual(shapes._pixel((1, 0, 0), self.BACK, self.RING, self.FILL), "#000000")
        self.assertEqual(shapes._pixel((0, 1, 0), self.BACK, self.RING, self.FILL), "#ff0000")
        self.assertEqual(shapes._pixel((0, 0, 1), self.BACK, self.RING, self.FILL), "#ffffff")

    def test_half_coverage_mixes(self):
        self.assertEqual(shapes._pixel((0.5, 0, 0.5), self.BACK, self.RING, self.FILL), "#808080")

    def test_channels(self):
        self.assertEqual(shapes._channels("#1F5FE0"), (31, 95, 224))


if __name__ == "__main__":
    unittest.main()
