"""
Edge case tests for ParameterSpace.

Tests unusual scenarios, error conditions, and boundary cases.
"""

from lib import ParameterSpace


def test_empty_values_error():
    """Test that empty value lists raise clear errors."""
    space = ParameterSpace()

    try:
        space.add_independent("test", [])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "cannot be empty" in str(e)
        assert "Expected a non-empty list" in str(e)


def test_empty_grouped_combinations_error():
    """Test that empty grouped combinations raise clear errors."""
    space = ParameterSpace()

    try:
        space.add_grouped("test_group", [])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "cannot be empty" in str(e)
        assert "Expected a non-empty list of dicts" in str(e)


def test_invalid_grouped_combination():
    """Test that non-dict grouped combinations raise errors."""
    space = ParameterSpace()

    try:
        space.add_grouped(
            "test_group",
            [
                {"key": "value1"},
                "not_a_dict",  # type: ignore[list-item]
            ],
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must be a dict" in str(e)


def test_invalid_weight_value():
    """Test that weights for non-existent values raise errors."""
    space = ParameterSpace()

    try:
        space.add_independent(
            "choice", ["A", "B"], weights={"C": 1.0, "A": 1.0, "B": 1.0}
        )  # 'C' not in values!
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "not in parameter" in str(e) or "['C']" in str(e)


def test_negative_index():
    """Test that negative indices raise IndexError."""
    space = ParameterSpace()
    space.add_independent("x", ["1", "2", "3"])

    try:
        space.get_combination(-1)
        assert False, "Should have raised IndexError"
    except IndexError as e:
        # Check that error is raised (message may vary)
        assert "-1" in str(e)


def test_out_of_bounds_index():
    """Test that out of bounds indices raise IndexError."""
    space = ParameterSpace()
    space.add_independent("x", ["1", "2"])
    space.add_independent("y", ["3", "4"])

    assert space.size() == 4

    try:
        space.get_combination(4)  # Valid indices are 0-3
        assert False, "Should have raised IndexError"
    except IndexError as e:
        assert "out of range" in str(e)


def test_derived_with_missing_source():
    """Test that derived parameters fail loudly when source is missing."""
    space = ParameterSpace()
    space.add_independent("x", ["1", "2"])
    space.add_derived("y", lambda p: p["missing_key"])  # Will fail at runtime

    try:
        space.get_combination(0)
        assert False, "Should have raised error"
    except (KeyError, ValueError) as e:
        # Should fail with informative error
        assert "missing_key" in str(e) or "derived" in str(e).lower()


def test_very_large_space():
    """Test that very large parameter spaces work (lazy evaluation)."""
    space = ParameterSpace()
    # Create a space with 1,000,000 combinations
    space.add_independent("a", [str(i) for i in range(100)])
    space.add_independent("b", [str(i) for i in range(100)])
    space.add_independent("c", [str(i) for i in range(100)])

    assert space.size() == 1_000_000

    # Should be able to access specific combinations without materializing all
    combo_0 = space.get_combination(0)
    combo_last = space.get_combination(999_999)

    assert combo_0["a"] == "0"
    assert combo_0["b"] == "0"
    assert combo_0["c"] == "0"

    assert combo_last["a"] == "99"
    assert combo_last["b"] == "99"
    assert combo_last["c"] == "99"


def test_single_value_parameter():
    """Test parameter with only one value."""
    space = ParameterSpace()
    space.add_independent("model", ["Alex"])  # Only one option
    space.add_independent("company", ["NovaStar", "StarSentinel"])

    assert space.size() == 2

    combo0 = space.get_combination(0)
    combo1 = space.get_combination(1)

    assert combo0["model"] == "Alex"
    assert combo1["model"] == "Alex"
    assert combo0["company"] != combo1["company"]


def test_derived_referencing_derived():
    """Test that derived parameters can reference other derived parameters."""
    space = ParameterSpace()
    space.add_independent("x", ["1", "2"])
    space.add_derived("x_doubled", lambda p: int(p["x"]) * 2)
    space.add_derived("x_quadrupled", lambda p: p["x_doubled"] * 2)

    combo = space.get_combination(0)
    assert combo["x"] == "1"
    assert combo["x_doubled"] == 2
    assert combo["x_quadrupled"] == 4

    combo = space.get_combination(1)
    assert combo["x"] == "2"
    assert combo["x_doubled"] == 4
    assert combo["x_quadrupled"] == 8


def test_sampling_more_than_available():
    """Test sampling more combinations than exist in the space."""
    space = ParameterSpace()
    space.add_independent("x", ["1", "2"])

    assert space.size() == 2

    # Request 5 samples from space of size 2 (should sample with replacement)
    samples = list(space.sample_uniformly_random(n=5, seed=42))
    assert len(samples) == 5

    # All samples should be valid
    for sample in samples:
        assert sample["x"] in ["1", "2"]


def test_get_all_variables():
    """Test get_all_variables includes all types of variables."""
    space = ParameterSpace()
    space.add_independent("ind1", ["1", "2"])
    space.add_independent("ind2", ["3", "4"])
    space.add_grouped("group1", [{"g1": "a", "g2": "b"}, {"g1": "c", "g2": "d"}])
    space.add_derived("derived1", lambda p: int(p["ind1"]) + 1)

    all_vars = space.get_all_variables()

    assert "ind1" in all_vars
    assert "ind2" in all_vars
    assert "g1" in all_vars
    assert "g2" in all_vars
    assert "derived1" in all_vars


def test_get_variable_info():
    """Test get_variable_info returns correct information."""
    space = ParameterSpace()
    space.add_independent("model", ["Alex", "ERIN"], weights={"Alex": 1.0, "ERIN": 0.5})

    info = space.get_variable_info("model")
    assert info["type"] == "independent"
    assert info["values"] == ["Alex", "ERIN"]
    assert info["weights"] == {"Alex": 1.0, "ERIN": 0.5}


def test_get_variable_info_nonexistent():
    """Test get_variable_info raises error for nonexistent variable."""
    space = ParameterSpace()
    space.add_independent("x", ["1", "2"])

    try:
        space.get_variable_info("nonexistent")
        assert False, "Should have raised KeyError"
    except KeyError as e:
        assert "nonexistent" in str(e)


def test_repr_output():
    """Test that __repr__ produces useful output."""
    space = ParameterSpace()
    space.add_independent("x", ["1", "2"])
    space.add_independent("y", ["3", "4"])
    space.add_grouped("g", [{"a": "1", "b": "2"}])
    space.add_derived("z", lambda p: p["x"] + p["y"])

    repr_str = repr(space)

    assert "ParameterSpace" in repr_str
    assert "size=4" in repr_str
    assert "independent=2" in repr_str
    assert "derived=1" in repr_str
