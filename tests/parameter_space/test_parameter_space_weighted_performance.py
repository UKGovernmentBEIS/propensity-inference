"""Test that weighted sampling performs well even with small weights."""

import time

from lib import ParameterSpace


def test_small_weights_many_axes():
    """Test weighted sampling with many axes having small weights."""
    space = ParameterSpace()

    # Create 20 binary axes, each with weights 1.0 and 0.5
    # This means average acceptance probability in rejection sampling would be (0.75)^20 ≈ 0.003
    for i in range(20):
        space.add_independent(
            f"axis_{i}", ["True", "False"], weights={"True": 1.0, "False": 0.5}
        )

    print(f"  Space size: {space.size():,}")
    print("  Number of weighted axes: 20")
    print(f"  Average weight product (rejection): (0.75)^20 ≈ {0.75**20:.6f}")

    # This should complete quickly (< 1 second)
    start = time.time()
    samples = list(space.sample_weighted(n=1000, seed=42))
    elapsed = time.time() - start

    print(f"  Generated 1000 samples in {elapsed:.3f}s")

    assert len(samples) == 1000

    # Count True values for each axis
    true_counts = {}
    for i in range(20):
        true_counts[i] = sum(1 for s in samples if s[f"axis_{i}"] == "True")

    # Each axis should have roughly 2:1 ratio (True:False)
    # With weight 1.0 vs 0.5, expected ratio is 2:1
    for i in range(20):
        ratio = true_counts[i] / (1000 - true_counts[i])
        # Should be roughly 2.0, allow some variance
        assert 1.5 < ratio < 2.5, f"axis_{i} has unexpected ratio {ratio:.2f}"

    # Performance check: should be much faster than 1s for 1000 samples
    assert elapsed < 1.0, f"Sampling took {elapsed:.3f}s, expected < 1.0s"


def test_extreme_weights():
    """Test with extremely small weights."""
    space = ParameterSpace()

    # Create scenario with very small weights
    # If we had 30 axes with 1.0 vs 0.1, average product would be (0.55)^30 ≈ 2e-8
    for i in range(30):
        space.add_independent(
            f"axis_{i}", ["high", "low"], weights={"high": 1.0, "low": 0.1}
        )

    print(f"  Space size: {space.size():,}")
    print("  Number of weighted axes: 30")
    print(f"  Average weight product (rejection): (0.55)^30 ≈ {0.55**30:.2e}")

    # This would take forever with rejection sampling
    # But should be fast with direct sampling
    start = time.time()
    samples = list(space.sample_weighted(n=500, seed=42))
    elapsed = time.time() - start

    print(f"  Generated 500 samples in {elapsed:.3f}s")

    assert len(samples) == 500

    # Count high values
    high_counts = sum(
        sum(1 for i in range(30) if s[f"axis_{i}"] == "high") for s in samples
    )
    total_values = 500 * 30

    # Expected: 1.0/(1.0+0.1) ≈ 90.9% high
    high_ratio = high_counts / total_values
    print(f"  High value ratio: {high_ratio:.3f} (expected ~0.909)")
    assert 0.85 < high_ratio < 0.95

    # Should still be fast
    assert elapsed < 2.0, f"Sampling took {elapsed:.3f}s, expected < 2.0s"


def test_weighted_correctness():
    """Test that weights are actually respected correctly."""
    space = ParameterSpace()

    # Simple test case
    space.add_independent(
        "choice", ["A", "B", "C"], weights={"A": 3.0, "B": 2.0, "C": 1.0}
    )

    samples = list(space.sample_weighted(n=6000, seed=42))
    counts = {"A": 0, "B": 0, "C": 0}
    for s in samples:
        counts[s["choice"]] += 1

    print(f"  Counts: A={counts['A']}, B={counts['B']}, C={counts['C']}")

    # Expected ratios: A:B:C = 3:2:1
    # So A should be ~50%, B ~33%, C ~17%
    total = sum(counts.values())
    ratios = {k: v / total for k, v in counts.items()}

    print(f"  Ratios: A={ratios['A']:.3f}, B={ratios['B']:.3f}, C={ratios['C']:.3f}")

    # Check ratios are approximately correct (within 10%)
    assert 0.45 < ratios["A"] < 0.55  # Expected 0.5
    assert 0.28 < ratios["B"] < 0.38  # Expected 0.333
    assert 0.12 < ratios["C"] < 0.22  # Expected 0.167


def test_mixed_weighted_unweighted():
    """Test space with both weighted and unweighted variables."""
    space = ParameterSpace()

    # Weighted variable
    space.add_independent(
        "weighted", ["high", "low"], weights={"high": 3.0, "low": 1.0}
    )

    # Unweighted variables (should be uniform)
    space.add_independent("uniform", ["X", "Y", "Z"])

    samples = list(space.sample_weighted(n=4000, seed=42))

    # Check weighted variable
    high_count = sum(1 for s in samples if s["weighted"] == "high")
    high_ratio = high_count / len(samples)
    assert 0.70 < high_ratio < 0.80  # Expected 0.75

    # Check unweighted variable is roughly uniform
    x_count = sum(1 for s in samples if s["uniform"] == "X")
    y_count = sum(1 for s in samples if s["uniform"] == "Y")
    z_count = sum(1 for s in samples if s["uniform"] == "Z")

    total = x_count + y_count + z_count
    x_ratio = x_count / total
    y_ratio = y_count / total
    z_ratio = z_count / total

    print(f"  Uniform ratios: X={x_ratio:.3f}, Y={y_ratio:.3f}, Z={z_ratio:.3f}")

    # Each should be roughly 1/3
    for ratio in [x_ratio, y_ratio, z_ratio]:
        assert 0.28 < ratio < 0.38  # Expected 0.333


def test_deterministic_with_seed():
    """Test that weighted sampling is deterministic with seed."""
    space = ParameterSpace()

    for i in range(10):
        space.add_independent(f"axis_{i}", ["0", "1"], weights={"0": 2.0, "1": 1.0})

    # Generate twice with same seed
    samples1 = list(space.sample_weighted(n=100, seed=999))
    samples2 = list(space.sample_weighted(n=100, seed=999))

    assert samples1 == samples2

    # Different seed should give different results
    samples3 = list(space.sample_weighted(n=100, seed=123))
    assert samples1 != samples3
