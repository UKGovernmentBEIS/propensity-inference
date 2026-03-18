"""Utility functions for propensity analysis.

This module contains shared utility functions used across the analysis pipeline.
"""

import numpy as np


def compute_eti(samples: np.ndarray, prob: float = 0.95) -> tuple[float, float]:
    """Compute equal-tailed interval (ETI) for a 1D sample array.

    The ETI is the central credible interval computed as the [alpha/2, 1-alpha/2]
    percentiles where alpha = 1 - prob. For prob=0.95, this gives the 2.5th and
    97.5th percentiles.

    This is a standard Bayesian credible interval that contains `prob` probability
    mass with equal tail probabilities on each side.

    Args:
        samples: 1D array of posterior samples.
        prob: Probability mass to include (default 0.95 for 95% interval).

    Returns:
        Tuple of (lower, upper) ETI bounds.

    Example:
        >>> samples = np.random.normal(0, 1, 10000)
        >>> lower, upper = compute_eti(samples, prob=0.95)
        >>> # lower ≈ -1.96, upper ≈ 1.96 for standard normal
    """
    # Remove NaN values
    clean_samples = samples[~np.isnan(samples)]
    if len(clean_samples) == 0:
        return (np.nan, np.nan)

    alpha = 1 - prob
    lower_pct = alpha / 2 * 100  # 2.5 for 95% interval
    upper_pct = (1 - alpha / 2) * 100  # 97.5 for 95% interval

    return (
        float(np.percentile(clean_samples, lower_pct)),
        float(np.percentile(clean_samples, upper_pct)),
    )
