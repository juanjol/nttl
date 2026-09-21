import numpy as np

from nttl.imaging.stats import frame_stats


def test_frame_stats_reports_robust_values():
    data = np.full((100, 100), 1000, dtype=np.uint16)
    data[:5, :] = 65535
    stats = frame_stats(data)
    assert stats.median == 1000
    assert stats.high_percentile >= 1000
    assert 0.04 < stats.saturated_fraction < 0.06
    assert 0.0 < stats.normalized_median < 1.0


def test_frame_stats_ignores_outliers_in_median():
    data = np.zeros((10, 10), dtype=np.uint16)
    data[0, 0] = 65535
    assert frame_stats(data).median == 0
