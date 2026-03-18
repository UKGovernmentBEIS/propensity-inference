"""Test weighted sampling for grouped variables."""

from lib import ParameterSpace


def test_grouped_weights_basic():
    """Test basic weighted sampling of grouped variables."""
    space = ParameterSpace()

    # Add weighted grouped variable
    space.add_grouped(
        "scenario",
        [
            {"type": "common", "difficulty": "easy"},
            {"type": "rare", "difficulty": "hard"},
        ],
        weights=[3.0, 1.0],
    )

    samples = list(space.sample_weighted(n=4000, seed=42))

    # Count occurrences
    common_count = sum(1 for s in samples if s["type"] == "common")
    rare_count = sum(1 for s in samples if s["type"] == "rare")

    print(f"  Common: {common_count}, Rare: {rare_count}")

    # Expected ratio: 3:1
    ratio = common_count / rare_count
    print(f"  Ratio: {ratio:.2f} (expected ~3.0)")

    assert 2.5 < ratio < 3.5, f"Unexpected ratio {ratio}"


def test_grouped_weights_validation():
    """Test that grouped weights are validated."""
    space = ParameterSpace()

    # Wrong length should fail
    try:
        space.add_grouped(
            "test", [{"a": "1"}, {"a": "2"}], weights=[1.0, 2.0, 3.0]
        )  # 3 weights for 2 combos!
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must match combinations length" in str(e)

    # Negative weights should fail
    try:
        space.add_grouped("test", [{"a": "1"}, {"a": "2"}], weights=[1.0, -1.0])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must be positive" in str(e)

    # Zero weights should fail
    try:
        space.add_grouped("test", [{"a": "1"}, {"a": "2"}], weights=[1.0, 0.0])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must be positive" in str(e)


def test_mixed_weighted_grouped_and_independent():
    """Test space with both weighted independent and weighted grouped variables."""
    space = ParameterSpace()

    # Weighted grouped
    space.add_grouped(
        "scenario",
        [{"type": "A", "sub": "x"}, {"type": "B", "sub": "y"}],
        weights=[2.0, 1.0],
    )

    # Weighted independent
    space.add_independent("choice", ["high", "low"], weights={"high": 3.0, "low": 1.0})

    samples = list(space.sample_weighted(n=4000, seed=42))

    # Check grouped weights
    type_a_count = sum(1 for s in samples if s["type"] == "A")
    type_b_count = sum(1 for s in samples if s["type"] == "B")
    print(f"  Type A: {type_a_count}, Type B: {type_b_count}")
    assert 1.5 < (type_a_count / type_b_count) < 2.5

    # Check independent weights
    high_count = sum(1 for s in samples if s["choice"] == "high")
    low_count = sum(1 for s in samples if s["choice"] == "low")
    print(f"  High: {high_count}, Low: {low_count}")
    assert 2.5 < (high_count / low_count) < 3.5


def test_multiple_weighted_groups():
    """Test multiple grouped variables, each with weights."""
    space = ParameterSpace()

    space.add_grouped(
        "group1", [{"g1_var": "common"}, {"g1_var": "rare"}], weights=[4.0, 1.0]
    )

    space.add_grouped(
        "group2", [{"g2_var": "frequent"}, {"g2_var": "infrequent"}], weights=[3.0, 1.0]
    )

    samples = list(space.sample_weighted(n=4000, seed=42))

    # Check group1 weights
    common_count = sum(1 for s in samples if s["g1_var"] == "common")
    rare_count = sum(1 for s in samples if s["g1_var"] == "rare")
    ratio1 = common_count / rare_count
    print(f"  Group1 ratio: {ratio1:.2f} (expected ~4.0)")
    assert 3.5 < ratio1 < 4.5

    # Check group2 weights
    freq_count = sum(1 for s in samples if s["g2_var"] == "frequent")
    infreq_count = sum(1 for s in samples if s["g2_var"] == "infrequent")
    ratio2 = freq_count / infreq_count
    print(f"  Group2 ratio: {ratio2:.2f} (expected ~3.0)")
    assert 2.5 < ratio2 < 3.5


def test_grouped_weights_deterministic():
    """Test that grouped weighted sampling is deterministic."""
    space = ParameterSpace()

    space.add_grouped(
        "test", [{"val": "A"}, {"val": "B"}, {"val": "C"}], weights=[1.0, 2.0, 3.0]
    )

    samples1 = list(space.sample_weighted(n=100, seed=999))
    samples2 = list(space.sample_weighted(n=100, seed=999))

    assert samples1 == samples2

    # Different seed should give different results
    samples3 = list(space.sample_weighted(n=100, seed=123))
    assert samples1 != samples3


def test_unweighted_grouped_still_works():
    """Test that unweighted grouped variables still work (uniform sampling)."""
    space = ParameterSpace()

    # Unweighted grouped
    space.add_grouped(
        "test", [{"val": "A"}, {"val": "B"}, {"val": "C"}]
    )  # No weights specified

    samples = list(space.sample_weighted(n=3000, seed=42))

    # Should be roughly uniform
    counts = {"A": 0, "B": 0, "C": 0}
    for s in samples:
        counts[s["val"]] += 1

    print(f"  Counts: {counts}")

    # Each should be roughly 1/3
    for count in counts.values():
        ratio = count / 3000
        assert 0.28 < ratio < 0.38
