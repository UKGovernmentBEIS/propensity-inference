"""Test that ParameterSpace works with truly massive spaces (> sys.maxsize)."""

import sys

from lib import ParameterSpace


def test_massive_space_size():
    """Test that we can represent spaces larger than sys.maxsize."""
    space = ParameterSpace()

    # Create a space with > sys.maxsize combinations
    # 100^20 = 1e40 combinations (way larger than sys.maxsize ≈ 9e18)
    for i in range(20):
        space.add_independent(f"param_{i}", [str(j) for j in range(100)])

    size = space.size()
    print(f"  Space size: {size:,}")
    assert size == 100**20
    assert size > sys.maxsize


def test_massive_space_get_combination():
    """Test that get_combination works for massive spaces."""
    space = ParameterSpace()

    # Create massive space
    for i in range(20):
        space.add_independent(f"param_{i}", [str(j) for j in range(100)])

    # Should be able to get combinations even though space is huge
    combo_0 = space.get_combination(0)
    assert all(combo_0[f"param_{i}"] == "0" for i in range(20))

    # Get a combination in the middle-ish
    large_index = 12345678901234567890  # Much larger than sys.maxsize
    if large_index < space.size():
        combo = space.get_combination(large_index)
        assert len(combo) == 20


def test_sample_uniformly_random_normal_space():
    """Test sample_uniformly_random works normally for regular-sized spaces."""
    space = ParameterSpace()
    space.add_independent("x", ["1", "2", "3"])
    space.add_independent("y", ["4", "5", "6"])

    samples = list(space.sample_uniformly_random(n=5, seed=42))
    assert len(samples) == 5

    # All samples should be valid
    for sample in samples:
        assert sample["x"] in ["1", "2", "3"]
        assert sample["y"] in ["4", "5", "6"]


def test_sample_uniformly_random_massive_space():
    """Test sample_uniformly_random works for massive spaces."""
    space = ParameterSpace()

    # Create space larger than sys.maxsize
    for i in range(20):
        space.add_independent(f"param_{i}", [str(j) for j in range(100)])

    size = space.size()
    assert size > sys.maxsize

    # Should be able to sample even though space is huge
    samples = list(space.sample_uniformly_random(n=10, seed=42))
    assert len(samples) == 10

    # All samples should be valid
    for sample in samples:
        assert len(sample) == 20
        for i in range(20):
            assert sample[f"param_{i}"] in [str(j) for j in range(100)]


def test_sample_weighted_normal_space():
    """Test sample_weighted works normally for regular-sized spaces."""
    space = ParameterSpace()
    space.add_independent(
        "choice", ["A", "B", "C"], weights={"A": 1.0, "B": 0.5, "C": 0.1}
    )

    samples = list(space.sample_weighted(n=50, seed=42))
    assert len(samples) == 50

    # Count occurrences
    counts = {"A": 0, "B": 0, "C": 0}
    for sample in samples:
        counts[sample["choice"]] += 1

    # A should appear most frequently
    assert counts["A"] > counts["B"]
    assert counts["B"] > counts["C"]


def test_sample_weighted_massive_space():
    """Test sample_weighted works for massive spaces."""
    space = ParameterSpace()

    # Create massive space with weights
    space.add_independent(
        "weighted", ["high", "low"], weights={"high": 1.0, "low": 0.1}
    )

    for i in range(19):
        space.add_independent(f"param_{i}", [str(j) for j in range(100)])

    size = space.size()
    assert size > sys.maxsize

    # Should be able to sample with weights
    samples = list(space.sample_weighted(n=20, seed=42))
    assert len(samples) == 20

    # Count weighted values
    high_count = sum(1 for s in samples if s["weighted"] == "high")
    low_count = sum(1 for s in samples if s["weighted"] == "low")

    # High should appear more often
    assert high_count > low_count
