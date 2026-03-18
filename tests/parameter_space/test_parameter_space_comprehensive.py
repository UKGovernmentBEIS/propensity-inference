"""
Comprehensive tests for ParameterSpace class (without pytest dependency).

Tests all major functionality:
- Independent variables
- Grouped variables
- Derived variables
- Weighted sampling
- Deterministic indexing
- Variable introspection
- Edge cases and error handling
"""

from datetime import datetime, timedelta

from lib import ParameterSpace


def test_empty_parameter_space():
    """Empty parameter space has size 1 (empty combination)."""
    params = ParameterSpace()
    assert params.size() == 1
    combo = params.get_combination(0)
    assert combo == {}


def test_single_independent_variable():
    """Single independent variable."""
    params = ParameterSpace()
    params.add_independent("model", ["Alex", "ERIN"])

    assert params.size() == 2
    assert params.get_combination(0) == {"model": "Alex"}
    assert params.get_combination(1) == {"model": "ERIN"}


def test_two_independent_variables():
    """Two independent variables create cartesian product."""
    params = ParameterSpace()
    params.add_independent("model", ["Alex", "ERIN"])
    params.add_independent("company", ["NovaStar", "StarSentinel"])

    assert params.size() == 4

    # Check all combinations
    combos = [params.get_combination(i) for i in range(4)]
    assert {"model": "Alex", "company": "NovaStar"} in combos
    assert {"model": "Alex", "company": "StarSentinel"} in combos
    assert {"model": "ERIN", "company": "NovaStar"} in combos
    assert {"model": "ERIN", "company": "StarSentinel"} in combos


def test_three_independent_variables():
    """Three independent variables."""
    params = ParameterSpace()
    params.add_independent("a", ["1", "2"])
    params.add_independent("b", ["3", "4", "5"])
    params.add_independent("c", ["6", "7"])

    # 2 * 3 * 2 = 12
    assert params.size() == 12


def test_index_out_of_range():
    """Accessing out of range index raises IndexError."""
    params = ParameterSpace()
    params.add_independent("model", ["Alex", "ERIN"])

    try:
        params.get_combination(2)
        assert False, "Should have raised IndexError"
    except IndexError:
        pass

    try:
        params.get_combination(-1)
        assert False, "Should have raised IndexError"
    except IndexError:
        pass


def test_single_group():
    """Single grouped variable set."""
    params = ParameterSpace()
    params.add_grouped(
        "model_pairs",
        [
            {"model": "Alex", "exfiltrating_model": "Alex"},
            {"model": "Alex", "exfiltrating_model": "ERIN"},
        ],
    )

    assert params.size() == 2
    assert params.get_combination(0) == {"model": "Alex", "exfiltrating_model": "Alex"}
    assert params.get_combination(1) == {"model": "Alex", "exfiltrating_model": "ERIN"}


def test_group_with_independent():
    """Grouped and independent variables combine."""
    params = ParameterSpace()
    params.add_independent("company", ["NovaStar", "StarSentinel"])
    params.add_grouped(
        "model_pairs",
        [
            {"model": "Alex", "exfiltrating_model": "Alex"},
            {"model": "Alex", "exfiltrating_model": "ERIN"},
        ],
    )

    # 2 companies * 2 model pairs = 4
    assert params.size() == 4

    combos = [params.get_combination(i) for i in range(4)]

    # Check that all combinations exist
    assert {
        "company": "NovaStar",
        "model": "Alex",
        "exfiltrating_model": "Alex",
    } in combos
    assert {
        "company": "NovaStar",
        "model": "Alex",
        "exfiltrating_model": "ERIN",
    } in combos
    assert {
        "company": "StarSentinel",
        "model": "Alex",
        "exfiltrating_model": "Alex",
    } in combos
    assert {
        "company": "StarSentinel",
        "model": "Alex",
        "exfiltrating_model": "ERIN",
    } in combos


def test_multiple_groups():
    """Multiple grouped variable sets."""
    params = ParameterSpace()
    params.add_grouped(
        "group1",
        [
            {"a": "1", "b": "2"},
            {"a": "3", "b": "4"},
        ],
    )
    params.add_grouped(
        "group2",
        [
            {"c": "5", "d": "6"},
            {"c": "7", "d": "8"},
            {"c": "9", "d": "10"},
        ],
    )

    # 2 * 3 = 6 combinations
    assert params.size() == 6


def test_simple_derived():
    """Simple derived variable."""
    params = ParameterSpace()
    params.add_independent("company", ["NovaStar", "StarSentinel"])
    params.add_derived("company_lowercase", lambda p: p["company"].lower())

    combo = params.get_combination(0)
    assert combo["company"] == "NovaStar"
    assert combo["company_lowercase"] == "novastar"

    combo = params.get_combination(1)
    assert combo["company"] == "StarSentinel"
    assert combo["company_lowercase"] == "starsentinel"


def test_derived_with_computation():
    """Derived variable with date computation."""
    params = ParameterSpace()
    params.add_independent("date", ["2025-02-10", "2025-05-12"])
    params.add_independent("days_until_threat", ["1", "4"])
    params.add_derived(
        "threat_date",
        lambda p: (
            datetime.strptime(p["date"], "%Y-%m-%d")
            + timedelta(days=int(p["days_until_threat"]))
        ).strftime("%Y-%m-%d"),
    )

    # Check first combination (date=2025-02-10, days=1)
    combo = params.get_combination(0)
    assert combo["date"] in ["2025-02-10", "2025-05-12"]
    assert combo["days_until_threat"] in ["1", "4"]
    # Verify threat_date is computed correctly from date + days_until_threat
    expected = (
        datetime.strptime(combo["date"], "%Y-%m-%d")
        + timedelta(days=int(combo["days_until_threat"]))
    ).strftime("%Y-%m-%d")
    assert combo["threat_date"] == expected


def test_derived_with_conditional():
    """Derived variable with conditional logic."""
    params = ParameterSpace()
    params.add_grouped(
        "threat_configs",
        [
            {"threat_timing": "today", "threat_time": "3 PM"},
            {"threat_timing": "future_date", "days_until_threat": "7"},
        ],
    )
    params.add_derived(
        "display_text",
        lambda p: (
            f"at {p['threat_time']}"
            if p["threat_timing"] == "today"
            else f"in {p['days_until_threat']} days"
        ),
    )

    combo0 = params.get_combination(0)
    assert combo0["display_text"] == "at 3 PM"

    combo1 = params.get_combination(1)
    assert combo1["display_text"] == "in 7 days"


def test_same_index_same_result():
    """Same index always returns same combination."""
    params = ParameterSpace()
    params.add_independent("model", ["Alex", "ERIN", "Claude"])
    params.add_independent("company", ["NovaStar", "StarSentinel"])

    # Get combination multiple times
    for _ in range(10):
        combo = params.get_combination(3)
        assert combo == params.get_combination(3)


def test_iteration_matches_indexing():
    """Iterating gives same results as indexing."""
    params = ParameterSpace()
    params.add_independent("a", ["1", "2", "3"])
    params.add_independent("b", ["4", "5"])

    # Collect via iteration
    iterated = list(params)

    # Collect via indexing
    indexed = [params.get_combination(i) for i in range(params.size())]

    assert iterated == indexed


def test_sample_uniformly_random():
    """Random sampling returns requested number of samples."""
    params = ParameterSpace()
    params.add_independent("model", ["Alex", "ERIN"])
    params.add_independent("company", ["NovaStar", "StarSentinel"])

    samples = list(params.sample_uniformly_random(n=3, seed=42))
    assert len(samples) == 3

    # All samples should be valid combinations
    for sample in samples:
        assert sample["model"] in ["Alex", "ERIN"]
        assert sample["company"] in ["NovaStar", "StarSentinel"]


def test_sample_uniformly_random_deterministic():
    """Same seed produces same samples."""
    params = ParameterSpace()
    params.add_independent("model", ["Alex", "ERIN", "Claude"])
    params.add_independent("company", ["NovaStar", "StarSentinel"])

    samples1 = list(params.sample_uniformly_random(n=5, seed=42))
    samples2 = list(params.sample_uniformly_random(n=5, seed=42))

    assert samples1 == samples2


def test_sample_uniformly_random_different_seeds():
    """Different seeds produce different samples."""
    params = ParameterSpace()
    params.add_independent("model", ["Alex", "ERIN", "Claude"])
    params.add_independent("company", ["NovaStar", "StarSentinel"])

    samples1 = list(params.sample_uniformly_random(n=10, seed=42))
    samples2 = list(params.sample_uniformly_random(n=10, seed=123))

    # Very likely to be different with 10 samples
    assert samples1 != samples2


def test_sample_weighted():
    """Weighted sampling respects weights."""
    params = ParameterSpace()
    params.add_independent(
        "choice", ["A", "B", "C"], weights={"A": 1.0, "B": 0.5, "C": 0.1}
    )

    # Sample many times
    samples = list(params.sample_weighted(n=100, seed=42))

    # Count occurrences
    counts = {"A": 0, "B": 0, "C": 0}
    for sample in samples:
        counts[sample["choice"]] += 1

    # A should appear more than B, B should appear more than C
    assert counts["A"] > counts["B"]
    assert counts["B"] > counts["C"]


def test_sample_weighted_deterministic():
    """Weighted sampling with same seed is deterministic."""
    params = ParameterSpace()
    params.add_independent("choice", ["A", "B"], weights={"A": 1.0, "B": 0.5})

    samples1 = list(params.sample_weighted(n=20, seed=42))
    samples2 = list(params.sample_weighted(n=20, seed=42))

    assert samples1 == samples2


def test_get_all_variables():
    """Get all variable names."""
    params = ParameterSpace()
    params.add_independent("model", ["Alex", "ERIN"])
    params.add_independent("company", ["NovaStar"])
    params.add_grouped(
        "threat_configs", [{"threat_type": "replacement", "threat_time": "3 PM"}]
    )
    params.add_derived("company_lowercase", lambda p: p["company"].lower())

    variables = params.get_all_variables()

    assert "model" in variables
    assert "company" in variables
    assert "threat_type" in variables
    assert "threat_time" in variables
    assert "company_lowercase" in variables


def test_get_variable_info_independent():
    """Get info for independent variable."""
    params = ParameterSpace()
    params.add_independent("model", ["Alex", "ERIN"])

    info = params.get_variable_info("model")
    assert info["type"] == "independent"
    assert info["values"] == ["Alex", "ERIN"]


def test_get_variable_info_with_weights():
    """Get info for independent variable with weights."""
    params = ParameterSpace()
    params.add_independent("choice", ["A", "B"], weights={"A": 1.0, "B": 0.5})

    info = params.get_variable_info("choice")
    assert info["type"] == "independent"
    assert info["weights"] == {"A": 1.0, "B": 0.5}


def test_get_variable_info_derived():
    """Get info for derived variable."""
    params = ParameterSpace()
    params.add_derived("computed", lambda p: "value")

    info = params.get_variable_info("computed")
    assert info["type"] == "derived"


def test_get_variable_info_grouped():
    """Get info for grouped variable."""
    params = ParameterSpace()
    params.add_grouped("pairs", [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}])

    info = params.get_variable_info("a")
    assert info["type"] == "grouped"
    assert isinstance(info["values"], list)
    assert set(info["values"]) == {"1", "3"}


def test_get_variable_info_grouped_with_weights():
    """Get info for grouped variable with weights."""
    params = ParameterSpace()
    params.add_grouped(
        "pairs",
        [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}, {"a": "5", "b": "6"}],
        weights=[1.0, 0.5, 0.2],
    )

    info = params.get_variable_info("a")
    assert info["type"] == "grouped"
    assert isinstance(info["values"], list)
    assert set(info["values"]) == {"1", "3", "5"}
    assert info["weights"] == [1.0, 0.5, 0.2]


def test_get_variable_info_nonexistent():
    """Getting info for nonexistent variable raises KeyError."""
    params = ParameterSpace()
    params.add_independent("model", ["Alex"])

    try:
        params.get_variable_info("nonexistent")
        assert False, "Should have raised KeyError"
    except KeyError:
        pass


def test_empty_values_list():
    """Adding independent variable with empty values raises error."""
    params = ParameterSpace()
    try:
        params.add_independent("model", [])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "cannot be empty" in str(e)


def test_empty_combinations_list():
    """Adding grouped variable with empty combinations raises error."""
    params = ParameterSpace()
    try:
        params.add_grouped("pairs", [])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "cannot be empty" in str(e)


def test_invalid_combination_type():
    """Adding grouped variable with non-dict combinations raises error."""
    params = ParameterSpace()
    try:
        params.add_grouped(
            "pairs",
            [
                {"a": 1},
                "not a dict",  # type: ignore[list-item]
            ],
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must be a dict" in str(e)


def test_weight_for_invalid_value():
    """Adding weight for value not in values list raises error."""
    params = ParameterSpace()
    try:
        params.add_independent(
            "model", ["Alex", "ERIN"], weights={"Claude": 1.0, "Alex": 1.0, "ERIN": 1.0}
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "not in" in str(e).lower()


def test_derived_variable_error():
    """Error in derived variable computation raises informative error."""
    params = ParameterSpace()
    params.add_independent("model", ["Alex"])
    params.add_derived("bad", lambda p: p["nonexistent_key"])

    try:
        params.get_combination(0)
        assert False, "Should have raised ValueError"
    except (ValueError, KeyError) as e:
        assert "derived" in str(e).lower() or "nonexistent_key" in str(e)


def test_repr():
    """String representation shows useful info."""
    params = ParameterSpace()
    params.add_independent("a", ["1", "2"])
    params.add_independent("b", ["3", "4"])
    params.add_derived("c", lambda p: p["a"] + p["b"])

    repr_str = repr(params)
    assert "ParameterSpace" in repr_str
    assert "size=4" in repr_str
    assert "independent=2" in repr_str
    assert "derived=1" in repr_str
