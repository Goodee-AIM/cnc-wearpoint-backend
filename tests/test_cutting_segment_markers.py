from pathlib import Path

import numpy as np
import pandas as pd
import unittest
import math
from scipy.ndimage import uniform_filter1d

from app.services.cutting_segment import describe_cutting_segment, extract_cutting_segment


def make_frame():
    rng = np.random.default_rng(42)
    count = 12000
    signal = rng.normal(0, 0.01, (count, 2))
    signal[2000:8000] += rng.normal(0, 3, (6000, 2))
    signal[9500:10500] += rng.normal(0, 3, (1000, 2))
    return pd.DataFrame({
        "acc": np.zeros(count), "audio": np.zeros(count),
        "force_x": signal[:, 0] + 2, "force_y": signal[:, 1] - 4,
        "force_z": np.zeros(count),
        "timestamp": pd.Timestamp("2023-03-02 11:52:02.268709") +
                     pd.to_timedelta(np.arange(count) * 613278, unit="ns"),
    })


class CuttingSegmentTests(unittest.TestCase):
    def test_matches_supplied_function(self):
        # 사용자가 제공한 원본 함수와 직접 비교합니다.
        source = Path(__file__).with_name("cutting_reference.txt").read_text(encoding="utf-8")
        namespace = {"np": np, "pd": pd, "uniform_filter1d": uniform_filter1d,
                     "CUT_WINDOW_MS": 50, "CUT_MIN_DURATION_MS": 100}
        exec(source, namespace)
        df = make_frame()
        for fs in (1000, 1617, 1630.5819, 20):
            expected = namespace["extract_cutting_segment"](df, fs)[1:]
            assert extract_cutting_segment(df, fs)[1:] == expected


    def test_nanosecond_sampling_and_longest_interval(self):
        df = make_frame()
        result = describe_cutting_segment(df.to_csv(index=False, header=False).encode())
        assert result["status"] == "ok"
        assert result["fs_hz"] == (1e9 / 613278)
        assert 1900 < result["start_idx"] < 2100
        assert 7900 < result["end_idx"] < 8100
        expected = (df.timestamp.iloc[result["start_idx"]] - df.timestamp.iloc[0]).value / 1e9
        assert result["start_seconds"] == expected


    def test_empty_constant_and_bad_force(self):
        df = make_frame().iloc[:100].copy()
        df[["force_x", "force_y"]] = 0
        with self.assertRaises(ValueError):
            extract_cutting_segment(df, 1000)
        with self.assertRaises(ValueError):
            extract_cutting_segment(df.iloc[:0], 1000)
        df.loc[0, "force_x"] = np.nan
        with self.assertRaises(ValueError):
            extract_cutting_segment(df, 1000)


    def test_file_end_uses_exclusive_boundary(self):
        df = make_frame()
        rng = np.random.default_rng(7)
        df["force_x"] = rng.normal(0, 0.01, len(df))
        df["force_y"] = rng.normal(0, 0.01, len(df))
        df.loc[6000:, "force_x"] += rng.normal(0, 3, 6000)
        df.loc[6000:, "force_y"] += rng.normal(0, 3, 6000)
        result = describe_cutting_segment(df.to_csv(index=False, header=False).encode())
        assert result["end_idx"] == len(df)
        assert math.isclose(result["end_seconds"], len(df) * 0.000613278)

if __name__ == "__main__":
    unittest.main()
