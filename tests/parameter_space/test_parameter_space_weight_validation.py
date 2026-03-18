"""Test weight validation for independent and grouped variables."""

from lib import ParameterSpace


def test_all_weights_specified():
    """Test that specifying all weights works."""
    space = ParameterSpace()

    # Should succeed - all values have weights
    space.add_independent(
        "choice", ["A", "B", "C"], weights={"A": 1.0, "B": 2.0, "C": 3.0}
    )

    assert "choice" in space._weights
    assert space._weights["choice"] == {"A": 1.0, "B": 2.0, "C": 3.0}


def test_no_weights_specified():
    """Test that omitting weights works (uniform sampling)."""
    space = ParameterSpace()

    # Should succeed - no weights means uniform
    space.add_independent("choice", ["A", "B", "C"])

    assert "choice" not in space._weights


def test_partial_weights_error():
    """Test that partial weights raise an error."""
    space = ParameterSpace()

    try:
        # Should fail - only A and B have weights, C is missing
        space.add_independent("choice", ["A", "B", "C"], weights={"A": 1.0, "B": 2.0})
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Weights must be specified for ALL values" in str(e)
        assert "Missing weights for: ['C']" in str(e)


def test_extra_weight_error():
    """Test that extra weights (for non-existent values) raise an error."""
    space = ParameterSpace()

    try:
        # Should fail - 'D' is not in values
        space.add_independent(
            "choice", ["A", "B", "C"], weights={"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0}
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "not in parameter" in str(e)
        assert "['D']" in str(e)


def test_non_numeric_weight_error():
    """Test that non-numeric weights raise TypeError."""
    # String weight
    space1 = ParameterSpace()
    try:
        space1.add_independent("choice", ["A", "B"], weights={"A": "2.0", "B": 1.0})  # type: ignore[dict-item]
        assert False, "Should have raised TypeError"
    except TypeError as e:
        assert "must be a number" in str(e)
        assert "str" in str(e)

    # None weight
    space2 = ParameterSpace()
    try:
        space2.add_independent("choice", ["A", "B"], weights={"A": None, "B": 1.0})  # type: ignore[dict-item]
        assert False, "Should have raised TypeError"
    except TypeError as e:
        assert "must be a number" in str(e)


def test_negative_weight_error():
    """Test that negative weights raise ValueError."""
    space = ParameterSpace()

    try:
        space.add_independent("choice", ["A", "B"], weights={"A": -1.0, "B": 1.0})
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must be positive" in str(e)


def test_zero_weight_error():
    """Test that zero weights raise ValueError."""
    space = ParameterSpace()

    try:
        space.add_independent("choice", ["A", "B"], weights={"A": 0.0, "B": 1.0})
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must be positive" in str(e)


def test_integer_weights():
    """Test that integer weights are accepted."""
    space = ParameterSpace()

    # Should succeed - integers are valid
    space.add_independent("choice", ["A", "B", "C"], weights={"A": 1, "B": 2, "C": 3})

    assert space._weights["choice"] == {"A": 1, "B": 2, "C": 3}


def test_mixed_int_float_weights():
    """Test that mixed int/float weights work."""
    space = ParameterSpace()

    # Should succeed
    space.add_independent("choice", ["A", "B", "C"], weights={"A": 1, "B": 2.5, "C": 3})

    assert space._weights["choice"] == {"A": 1, "B": 2.5, "C": 3}


def test_grouped_weights_validation():
    """Test that grouped weights are validated similarly."""
    space = ParameterSpace()

    # Valid - all weights specified
    space.add_grouped(
        "test", [{"val": "A"}, {"val": "B"}, {"val": "C"}], weights=[1.0, 2.0, 3.0]
    )

    # Invalid - wrong length
    try:
        space.add_grouped(
            "test2", [{"val": "X"}, {"val": "Y"}], weights=[1.0, 2.0, 3.0]
        )  # 3 weights for 2 combos
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must match combinations length" in str(e)

    # Invalid - negative weight
    try:
        space.add_grouped("test3", [{"val": "X"}, {"val": "Y"}], weights=[1.0, -2.0])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must be positive" in str(e)


def test_weighted_sampling_with_validation():
    """Test that validated weights work correctly in sampling."""
    space = ParameterSpace()

    # All weights specified
    space.add_independent(
        "choice", ["A", "B", "C"], weights={"A": 3.0, "B": 2.0, "C": 1.0}
    )

    samples = list(space.sample_weighted(n=6000, seed=42))

    counts = {"A": 0, "B": 0, "C": 0}
    for s in samples:
        counts[s["choice"]] += 1

    # Check ratios are approximately 3:2:1
    total = sum(counts.values())
    ratios = {k: v / total for k, v in counts.items()}

    print(f"  Ratios: A={ratios['A']:.3f}, B={ratios['B']:.3f}, C={ratios['C']:.3f}")

    # A should be ~0.5 (3/6), B ~0.333 (2/6), C ~0.167 (1/6)
    assert 0.45 < ratios["A"] < 0.55
    assert 0.28 < ratios["B"] < 0.38
    assert 0.12 < ratios["C"] < 0.22


def test_unweighted_sampling_still_works():
    """Test that unweighted parameters still sample uniformly."""
    space = ParameterSpace()

    # No weights - should be uniform
    space.add_independent("choice", ["A", "B", "C"])

    samples = list(space.sample_weighted(n=3000, seed=42))

    counts = {"A": 0, "B": 0, "C": 0}
    for s in samples:
        counts[s["choice"]] += 1

    # Should be roughly uniform
    for count in counts.values():
        ratio = count / 3000
        assert 0.28 < ratio < 0.38
