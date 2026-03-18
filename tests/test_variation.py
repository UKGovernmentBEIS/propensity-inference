"""
Tests for lib/variation.py - Variation class and functionality.
"""

import pytest

from lib.parameter_space import ParameterSpace
from lib.variation import Variation, WeightedSuite


def create_test_suite_a() -> ParameterSpace:
    """Create test suite A with shared + suite-specific params."""
    space = ParameterSpace()
    space.add_independent("shared_param1", ["value1", "value2"])
    space.add_independent("shared_param2", ["yes", "no"])
    space.add_independent("suite_a_param", ["a1", "a2"])
    return space


def create_test_suite_b() -> ParameterSpace:
    """Create test suite B with shared + suite-specific params."""
    space = ParameterSpace()
    space.add_independent("shared_param1", ["value1", "value2"])
    space.add_independent("shared_param2", ["yes", "no"])
    space.add_independent("suite_b_param", ["b1", "b2"])
    return space


def create_test_suite_c() -> ParameterSpace:
    """Create test suite C with only shared params."""
    space = ParameterSpace()
    space.add_independent("shared_param1", ["value1", "value2"])
    space.add_independent("shared_param2", ["yes", "no"])
    return space


class TestVariation:
    """Tests for Variation class."""

    def test_creation_basic(self):
        """Test basic Variation creation with required suite_weights."""
        variation = Variation(
            name="test_variation",
            suites={
                "suite_a": create_test_suite_a,
                "suite_b": create_test_suite_b,
            },
            suite_weights={"suite_a": 1.0, "suite_b": 1.0},
        )

        assert variation.name == "test_variation"
        assert len(variation.suites) == 2
        assert "suite_a" in variation.suites
        assert "suite_b" in variation.suites
        assert variation.suite_weights == {"suite_a": 1.0, "suite_b": 1.0}

    def test_creation_with_weights(self):
        """Test Variation creation with different suite weights."""
        variation = Variation(
            name="test_variation",
            suites={
                "suite_a": create_test_suite_a,
                "suite_b": create_test_suite_b,
            },
            suite_weights={"suite_a": 1.0, "suite_b": 3.0},
        )

        assert variation.suite_weights["suite_a"] == 1.0
        assert variation.suite_weights["suite_b"] == 3.0
        assert variation.get_total_weight() == 4.0

    def test_missing_suite_weights_raises_error(self):
        """Test that missing suite_weights raises TypeError."""
        with pytest.raises(TypeError):
            Variation(  # type: ignore[call-arg]
                name="test_variation",
                suites={
                    "suite_a": create_test_suite_a,
                    "suite_b": create_test_suite_b,
                },
                # suite_weights intentionally omitted
            )

    def test_mismatched_suite_weights_raises_error(self):
        """Test that mismatched suite_weights keys raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Variation(
                name="test_variation",
                suites={
                    "suite_a": create_test_suite_a,
                    "suite_b": create_test_suite_b,
                },
                suite_weights={"suite_a": 1.0, "suite_c": 2.0},  # suite_c doesn't exist
            )
        assert "Suites missing weights" in str(exc_info.value)
        assert "Weights for non-existent suites" in str(exc_info.value)

    def test_non_positive_weight_raises_error(self):
        """Test that non-positive weights raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Variation(
                name="test_variation",
                suites={"suite_a": create_test_suite_a},
                suite_weights={"suite_a": 0.0},
            )
        assert "non-positive weight" in str(exc_info.value)

        with pytest.raises(ValueError):
            Variation(
                name="test_variation",
                suites={"suite_a": create_test_suite_a},
                suite_weights={"suite_a": -1.0},
            )

    def test_get_weighted_suites(self):
        """Test get_weighted_suites returns WeightedSuite namedtuples."""
        variation = Variation(
            name="test_variation",
            suites={
                "suite_a": create_test_suite_a,
                "suite_b": create_test_suite_b,
            },
            suite_weights={"suite_a": 1.0, "suite_b": 3.0},
        )

        weighted = variation.get_weighted_suites()

        assert len(weighted) == 2
        assert all(isinstance(ws, WeightedSuite) for ws in weighted)

        # Find suite_a and suite_b
        suite_a = next(ws for ws in weighted if ws.name == "suite_a")
        suite_b = next(ws for ws in weighted if ws.name == "suite_b")

        assert suite_a.weight == 1.0
        assert suite_b.weight == 3.0
        assert callable(suite_a.space_factory)
        assert callable(suite_b.space_factory)

    def test_get_all_parameters(self):
        """Test get_all_parameters returns union of all suite parameters."""
        variation = Variation(
            name="test_variation",
            suites={
                "suite_a": create_test_suite_a,
                "suite_b": create_test_suite_b,
            },
            suite_weights={"suite_a": 1.0, "suite_b": 1.0},
        )

        all_params = variation.get_all_parameters()

        # Should have all shared params plus suite-specific params
        expected = {
            "shared_param1",
            "shared_param2",
            "suite_a_param",
            "suite_b_param",
        }
        assert all_params == expected

    def test_get_shared_parameters(self):
        """Test get_shared_parameters returns only params in all suites."""
        variation = Variation(
            name="test_variation",
            suites={
                "suite_a": create_test_suite_a,
                "suite_b": create_test_suite_b,
                "suite_c": create_test_suite_c,
            },
            suite_weights={"suite_a": 1.0, "suite_b": 1.0, "suite_c": 1.0},
        )

        shared = variation.get_shared_parameters()

        # Only the params present in all three suites
        expected = {"shared_param1", "shared_param2"}
        assert shared == expected

    def test_get_suite_specific_parameters(self):
        """Test get_suite_specific_parameters identifies unique params per suite."""
        variation = Variation(
            name="test_variation",
            suites={
                "suite_a": create_test_suite_a,
                "suite_b": create_test_suite_b,
                "suite_c": create_test_suite_c,
            },
            suite_weights={"suite_a": 1.0, "suite_b": 1.0, "suite_c": 1.0},
        )

        suite_specific = variation.get_suite_specific_parameters()

        # Suite A has suite_a_param that others don't
        assert "suite_a" in suite_specific
        assert suite_specific["suite_a"] == {"suite_a_param"}

        # Suite B has suite_b_param that others don't
        assert "suite_b" in suite_specific
        assert suite_specific["suite_b"] == {"suite_b_param"}

        # Suite C has no suite-specific params (only shared)
        assert "suite_c" not in suite_specific

    def test_get_suite_names(self):
        """Test get_suite_names returns list of suite names."""
        variation = Variation(
            name="test_variation",
            suites={
                "suite_a": create_test_suite_a,
                "suite_b": create_test_suite_b,
            },
            suite_weights={"suite_a": 1.0, "suite_b": 1.0},
        )

        suite_names = variation.get_suite_names()

        assert len(suite_names) == 2
        assert "suite_a" in suite_names
        assert "suite_b" in suite_names

    def test_repr(self):
        """Test __repr__ produces readable string."""
        variation = Variation(
            name="test_variation",
            suites={
                "suite_a": create_test_suite_a,
                "suite_b": create_test_suite_b,
            },
            suite_weights={"suite_a": 1.0, "suite_b": 1.0},
        )

        repr_str = repr(variation)

        assert "test_variation" in repr_str
        assert "suite_a" in repr_str
        assert "suite_b" in repr_str

    def test_empty_variation(self):
        """Test Variation with no suites."""
        variation = Variation(name="empty_variation", suites={}, suite_weights={})

        assert variation.get_all_parameters() == set()
        assert variation.get_shared_parameters() == set()
        assert variation.get_suite_specific_parameters() == {}
        assert variation.get_suite_names() == []

    def test_single_suite_variation(self):
        """Test Variation with only one suite."""
        variation = Variation(
            name="single_suite",
            suites={"suite_a": create_test_suite_a},
            suite_weights={"suite_a": 1.0},
        )

        all_params = variation.get_all_parameters()
        shared_params = variation.get_shared_parameters()

        # With only one suite, all params are "shared" (no comparison possible)
        assert all_params == shared_params
        suite_specific = variation.get_suite_specific_parameters()
        assert len(suite_specific) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
