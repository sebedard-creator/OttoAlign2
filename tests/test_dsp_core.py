import unittest

import numpy as np

from dsp_core import dynamic_align


class DynamicAlignTests(unittest.TestCase):
    def test_short_input_returns_a_pair_and_zero_delay_curve(self):
        target = np.arange(100, dtype=np.float64)

        aligned, delays = dynamic_align(target, target, 48_000)

        np.testing.assert_array_equal(aligned, target)
        np.testing.assert_array_equal(delays, np.zeros(len(target)))

    def test_integer_delays_are_corrected_in_both_directions(self):
        rng = np.random.default_rng(1234)
        sample_rate = 48_000
        source = np.convolve(
            rng.normal(0, 0.2, sample_rate // 2),
            np.ones(9) / 9,
            mode="same",
        )
        for delay in (-7, 12):
            with self.subTest(delay=delay):
                if delay > 0:
                    target = np.concatenate((np.zeros(delay), source[:-delay]))
                else:
                    width = -delay
                    target = np.concatenate((source[width:], np.zeros(width)))

                aligned, curve = dynamic_align(target, source, sample_rate)

                self.assertAlmostEqual(float(np.median(curve)), delay, places=6)
                np.testing.assert_allclose(
                    aligned[100:-100],
                    source[100:-100],
                    atol=1e-10,
                )


if __name__ == "__main__":
    unittest.main()
