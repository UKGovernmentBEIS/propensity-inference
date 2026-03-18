"""Simple tests for ParameterSpace without pytest dependency."""

from datetime import datetime, timedelta

from lib import ParameterSpace


def test_basic_independent():
    """Test basic independent variables."""
    params = ParameterSpace()
    params.add_independent("model", ["Alex", "ERIN"])
    params.add_independent("company", ["NovaStar", "StarSentinel"])

    assert params.size() == 4, f"Expected 4, got {params.size()}"

    combo0 = params.get_combination(0)
    assert "model" in combo0
    assert "company" in combo0


def test_grouped_variables():
    """Test grouped variables."""
    params = ParameterSpace()
    params.add_grouped(
        "model_pairs",
        [
            {"model": "Alex", "exfiltrating_model": "Alex"},
            {"model": "Alex", "exfiltrating_model": "ERIN"},
        ],
    )

    assert params.size() == 2, f"Expected 2, got {params.size()}"

    combo0 = params.get_combination(0)
    assert combo0 == {"model": "Alex", "exfiltrating_model": "Alex"}

    combo1 = params.get_combination(1)
    assert combo1 == {"model": "Alex", "exfiltrating_model": "ERIN"}


def test_derived_variables():
    """Test derived variables."""
    params = ParameterSpace()
    params.add_independent("company", ["NovaStar", "StarSentinel"])
    params.add_derived("company_lowercase", lambda p: p["company"].lower())

    combo0 = params.get_combination(0)
    assert combo0["company"] == "NovaStar"
    assert combo0["company_lowercase"] == "novastar"

    combo1 = params.get_combination(1)
    assert combo1["company"] == "StarSentinel"
    assert combo1["company_lowercase"] == "starsentinel"


def test_derived_with_dates():
    """Test derived variables with date computations."""
    params = ParameterSpace()
    params.add_independent("date", ["2025-02-10"])
    params.add_independent("days_until_threat", ["1", "4"])
    params.add_derived(
        "threat_date",
        lambda p: (
            datetime.strptime(p["date"], "%Y-%m-%d")
            + timedelta(days=int(p["days_until_threat"]))
        ).strftime("%Y-%m-%d"),
    )

    combo0 = params.get_combination(0)
    assert combo0["date"] == "2025-02-10"
    assert combo0["days_until_threat"] == "1"
    assert combo0["threat_date"] == "2025-02-11"

    combo1 = params.get_combination(1)
    assert combo1["days_until_threat"] == "4"
    assert combo1["threat_date"] == "2025-02-14"


def test_combined():
    """Test combination of all types."""
    params = ParameterSpace()
    params.add_independent("company", ["NovaStar", "StarSentinel"])
    params.add_grouped(
        "model_pairs",
        [
            {"model": "Alex", "exfiltrating_model": "Alex"},
            {"model": "Alex", "exfiltrating_model": "ERIN"},
        ],
    )
    params.add_derived("company_lowercase", lambda p: p["company"].lower())

    # 2 companies * 2 model pairs = 4
    assert params.size() == 4

    # Check all combinations have all fields
    for i in range(params.size()):
        combo = params.get_combination(i)
        assert "company" in combo
        assert "model" in combo
        assert "exfiltrating_model" in combo
        assert "company_lowercase" in combo
        assert combo["company_lowercase"] == combo["company"].lower()


def test_deterministic_indexing():
    """Test that indexing is deterministic."""
    params = ParameterSpace()
    params.add_independent("a", ["1", "2", "3"])
    params.add_independent("b", ["4", "5"])

    # Same index should always return same result
    for i in range(params.size()):
        combo1 = params.get_combination(i)
        combo2 = params.get_combination(i)
        assert combo1 == combo2

    # Iteration should match indexing
    iterated = list(params)
    indexed = [params.get_combination(i) for i in range(params.size())]
    assert iterated == indexed


def test_sampling():
    """Test random sampling."""
    params = ParameterSpace()
    params.add_independent("model", ["Alex", "ERIN", "Claude"])
    params.add_independent("company", ["NovaStar", "StarSentinel"])

    # Sample with seed
    samples1 = list(params.sample_uniformly_random(n=5, seed=42))
    samples2 = list(params.sample_uniformly_random(n=5, seed=42))

    assert len(samples1) == 5
    assert len(samples2) == 5
    assert samples1 == samples2  # Same seed = same samples

    # Different seed
    samples3 = list(params.sample_uniformly_random(n=5, seed=123))
    assert samples3 != samples1


def test_weighted_sampling():
    """Test weighted sampling."""
    params = ParameterSpace()
    params.add_independent(
        "choice", ["A", "B", "C"], weights={"A": 1.0, "B": 0.5, "C": 0.1}
    )

    # Sample many times
    samples = list(params.sample_weighted(n=100, seed=42))
    assert len(samples) == 100

    # Count occurrences
    counts = {"A": 0, "B": 0, "C": 0}
    for sample in samples:
        counts[sample["choice"]] += 1

    # A should appear most, then B, then C
    assert counts["A"] > counts["B"] > counts["C"] or counts["C"] < 20


def test_remove_independent():
    """Test removing an independent parameter."""
    params = ParameterSpace()
    params.add_independent("a", ["1", "2"])
    params.add_independent("b", ["3", "4"])
    params.add_independent("c", ["5", "6"])

    assert params.size() == 8  # 2 * 2 * 2

    params.remove("b")

    assert params.size() == 4  # 2 * 2
    combo = params.get_combination(0)
    assert "a" in combo
    assert "c" in combo
    assert "b" not in combo


def test_remove_nonexistent_raises():
    """Test that removing nonexistent parameter raises KeyError."""
    params = ParameterSpace()
    params.add_independent("a", ["1", "2"])

    try:
        params.remove("nonexistent")
        assert False, "Should have raised KeyError"
    except KeyError as e:
        assert "nonexistent" in str(e)


def test_remove_grouped_raises():
    """Test that removing grouped parameter raises KeyError."""
    params = ParameterSpace()
    params.add_grouped("group", [{"x": "1"}, {"x": "2"}])

    try:
        params.remove("group")
        assert False, "Should have raised KeyError"
    except KeyError as e:
        assert "independent" in str(e).lower()
