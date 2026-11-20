"""Shared helpers for the feature and model scripts."""
import numpy as np


def lpct(s):
    """Within-group percentile, same formula as win_pct_percentile (D10, D59): (average rank - 1)/(n - 1) * 100
    over non-missing values; 0 = lowest, 100 = highest; NaN stays NaN (all NaN if fewer than 2 values)."""
    r = s.rank(method="average")
    n = s.notna().sum()
    return (r - 1) / (n - 1) * 100 if n > 1 else r * np.nan
