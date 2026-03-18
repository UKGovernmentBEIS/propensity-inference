"""Tests for placeholder filling and feature zeroing in pooled regression.

These tests verify the two-step process for handling unimplemented parameters:
1. fill_unimplemented_with_placeholder() fills NaN with valid categories
2. zero_unimplemented_features() zeros effect-coded feature columns

Run with: uv run pytest tests/pooled_fitting/test_placeholder_and_zeroing.py -v
"""

from dataclasses import dataclass
from typing import Any

import jax.numpy as jnp
import numpy as np
import pandas as pd
import pytest

from lib.pooled_fitting.data_prep import fill_unimplemented_with_placeholder
from lib.pooled_fitting.feature_zeroing import (
    build_goal_value_inapplicable_mask,
    zero_unimplemented_features,
)


# Test fixtures and mock objects
@dataclass
class MockState:
    """Mock HiBayES state object with features dict."""

    features: dict[str, Any] | None = None


@pytest.fixture
def sample_category_order():
    """Sample category order for testing."""
    return {
        "goal_present": ["true", "false", "_DUMMY_"],
        "goal_conflict": ["true", "false", "_DUMMY_"],
        "threat": ["replacement", "other", "none", "_DUMMY_"],
        "independence": ["neutral", "encourage_independence", "_DUMMY_"],
    }


@pytest.fixture
def sample_param_implementation():
    """Sample parameter implementation mapping."""
    return {
        "scenario_A": ["goal_present", "goal_conflict", "threat"],
        "scenario_B": ["threat", "independence"],
        "scenario_C": ["goal_present", "goal_conflict", "independence"],
    }


# =============================================================================
# Tests for fill_unimplemented_with_placeholder
# =============================================================================


class TestFillUnimplementedWithPlaceholder:
    """Tests for fill_unimplemented_with_placeholder()."""

    def test_fills_nan_for_unimplemented_params(
        self, sample_category_order, sample_param_implementation
    ):
        """NaN values for unimplemented params should be filled with placeholder."""
        df = pd.DataFrame(
            {
                "scenario": ["scenario_A", "scenario_A", "scenario_B"],
                "goal_present": ["true", "false", np.nan],  # Not implemented in B
                "goal_conflict": ["true", "true", np.nan],  # Not implemented in B
                "threat": ["replacement", "other", "none"],
                "independence": [np.nan, np.nan, "neutral"],  # Not implemented in A
            }
        )

        result = fill_unimplemented_with_placeholder(
            df,
            all_params=["goal_present", "goal_conflict", "threat", "independence"],
            category_order=sample_category_order,
            param_implementation=sample_param_implementation,
        )

        # Unimplemented params should be filled
        assert result.loc[2, "goal_present"] == "true"  # First non-_DUMMY_ category
        assert result.loc[2, "goal_conflict"] == "true"
        assert result.loc[0, "independence"] == "neutral"
        assert result.loc[1, "independence"] == "neutral"

        # Implemented params should NOT be changed
        assert result.loc[0, "goal_present"] == "true"
        assert result.loc[1, "goal_present"] == "false"
        assert result.loc[2, "threat"] == "none"

    def test_does_not_fill_nan_for_implemented_params(
        self, sample_category_order, sample_param_implementation
    ):
        """NaN for implemented params should remain (will cause effect coding to fail)."""
        df = pd.DataFrame(
            {
                "scenario": ["scenario_A", "scenario_A"],
                "goal_present": ["true", np.nan],  # NaN for implemented param = bug
                "goal_conflict": ["true", "false"],
                "threat": ["replacement", "other"],
            }
        )

        result = fill_unimplemented_with_placeholder(
            df,
            all_params=["goal_present", "goal_conflict", "threat"],
            category_order=sample_category_order,
            param_implementation=sample_param_implementation,
        )

        # NaN should remain - this is a data bug that should cause effect coding to fail
        assert pd.isna(result.loc[1, "goal_present"])

    def test_placeholder_is_first_non_dummy_category(self, sample_param_implementation):
        """Placeholder should be first category that isn't _DUMMY_."""
        category_order = {
            "some_param": ["alpha", "beta", "gamma", "_DUMMY_"],
        }
        param_implementation = {
            "scenario_X": [],  # Doesn't implement any params
        }

        df = pd.DataFrame(
            {
                "scenario": ["scenario_X"],
                "some_param": [np.nan],
            }
        )

        result = fill_unimplemented_with_placeholder(
            df,
            all_params=["some_param"],
            category_order=category_order,
            param_implementation=param_implementation,
        )

        assert result.loc[0, "some_param"] == "alpha"


# =============================================================================
# Tests for zero_unimplemented_features
# =============================================================================


class TestZeroUnimplementedFeatures:
    """Tests for zero_unimplemented_features()."""

    def test_zeros_features_for_non_implementing_scenarios(
        self, sample_param_implementation
    ):
        """Features should be zeroed for scenarios that don't implement the param."""
        # Create mock state with effect-coded features
        state = MockState(
            features={
                "model_variation[model_A_var_1]": jnp.array([1.0, 1.0, -1.0]),
                "goal_present[true]": jnp.array(
                    [1.0, -1.0, 0.5]
                ),  # scenario_B doesn't implement
                "threat[replacement]": jnp.array([1.0, 0.0, -1.0]),  # All implement
            }
        )

        df = pd.DataFrame(
            {
                "scenario": ["scenario_A", "scenario_A", "scenario_B"],
                "variation": ["var_1", "var_1", "var_1"],
            }
        )

        result = zero_unimplemented_features(
            state, df, param_implementation=sample_param_implementation
        )

        # goal_present should be zeroed for scenario_B (index 2)
        goal_present_arr = np.array(result.features["goal_present[true]"])
        assert goal_present_arr[0] == 1.0  # scenario_A implements
        assert goal_present_arr[1] == -1.0  # scenario_A implements
        assert goal_present_arr[2] == 0.0  # scenario_B doesn't implement - ZEROED

        # threat should NOT be zeroed (all scenarios implement)
        threat_arr = np.array(result.features["threat[replacement]"])
        assert threat_arr[0] == 1.0
        assert threat_arr[1] == 0.0
        assert threat_arr[2] == -1.0

    def test_model_variation_never_zeroed(self, sample_param_implementation):
        """model_variation is the intercept and should NEVER be zeroed."""
        state = MockState(
            features={
                "model_variation[model_A_var_1]": jnp.array([1.0, -1.0]),
            }
        )

        df = pd.DataFrame(
            {
                "scenario": ["scenario_A", "scenario_B"],
                "variation": ["var_1", "var_1"],
            }
        )

        # model_variation should never be zeroed regardless of param_implementation
        result = zero_unimplemented_features(
            state, df, param_implementation=sample_param_implementation
        )

        mv_arr = np.array(result.features["model_variation[model_A_var_1]"])
        assert mv_arr[0] == 1.0
        assert mv_arr[1] == -1.0

    def test_handles_none_features(self):
        """Should handle state with None features gracefully."""
        state = MockState(features=None)
        df = pd.DataFrame({"scenario": ["scenario_A"]})

        result = zero_unimplemented_features(state, df)
        assert result.features is None


# =============================================================================
# Tests for goal_value special handling
# =============================================================================


class TestGoalValueSpecialHandling:
    """Tests for goal_value zeroing when goal_conflict=false AND goal_present=false."""

    def test_build_goal_value_inapplicable_mask(self):
        """goal_value is inapplicable when BOTH goal_conflict=false AND goal_present=false."""
        df = pd.DataFrame(
            {
                "goal_conflict": ["true", "false", "false", "true"],
                "goal_present": ["true", "true", "false", "false"],
            }
        )

        mask = build_goal_value_inapplicable_mask(df)

        assert mask[0] is np.False_  # conflict=true, present=true -> applicable
        assert mask[1] is np.False_  # conflict=false, present=true -> applicable
        assert mask[2] is np.True_  # conflict=false, present=false -> INAPPLICABLE
        assert mask[3] is np.False_  # conflict=true, present=false -> applicable

    def test_goal_value_harmonized_zeroed_when_both_false(self):
        """goal_value_harmonized features zeroed when goal_conflict=false AND goal_present=false.

        This tests the real-world case: goal_value_harmonized is used with --goal flag,
        and has special handling in zero_unimplemented_features that:
        1. Zeros for non-implementing scenarios
        2. Zeros when both goal_conflict and goal_present are false
        """
        param_implementation = {
            "scenario_A": ["goal_value_harmonized", "goal_conflict", "goal_present"],
        }

        state = MockState(
            features={
                "goal_value_harmonized[safety]": jnp.array([1.0, 0.5, -0.5]),
            }
        )

        df = pd.DataFrame(
            {
                "scenario": ["scenario_A", "scenario_A", "scenario_A"],
                "variation": ["v1", "v1", "v1"],
                "goal_conflict": ["true", "false", "false"],
                "goal_present": ["true", "true", "false"],  # Index 2: both false
            }
        )

        result = zero_unimplemented_features(
            state,
            df,
            param_implementation=param_implementation,
        )

        goal_value_arr = np.array(result.features["goal_value_harmonized[safety]"])
        assert goal_value_arr[0] == 1.0  # Both not false -> keep
        assert goal_value_arr[1] == 0.5  # goal_present=true -> keep
        assert goal_value_arr[2] == 0.0  # BOTH false -> ZEROED

    def test_goal_value_mask_handles_missing_columns(self):
        """Should return all-False mask if goal_conflict or goal_present columns missing."""
        df = pd.DataFrame({"other_column": ["a", "b"]})

        mask = build_goal_value_inapplicable_mask(df)

        assert not mask.any()


# =============================================================================
# Integration tests
# =============================================================================


class TestPlaceholderAndZeroingIntegration:
    """Integration tests for the full placeholder + zeroing pipeline."""

    def test_placeholder_choice_doesnt_affect_zeroed_result(
        self, sample_category_order, sample_param_implementation
    ):
        """The placeholder value doesn't matter because features get zeroed anyway."""
        # This test verifies the key insight: any placeholder works because zeroing
        # removes the contribution regardless of what value was filled.

        df = pd.DataFrame(
            {
                "scenario": ["scenario_B"],  # Doesn't implement goal_present
                "goal_present": [np.nan],
                "threat": ["replacement"],
            }
        )

        # Fill with placeholder
        filled = fill_unimplemented_with_placeholder(
            df,
            all_params=["goal_present", "threat"],
            category_order=sample_category_order,
            param_implementation=sample_param_implementation,
        )

        # The placeholder is "true" (first non-_DUMMY_ category)
        assert filled.loc[0, "goal_present"] == "true"

        # Now if we had effect-coded this and then zeroed, the feature would be 0
        # regardless of whether placeholder was "true" or "false"
        state = MockState(
            features={
                # Pretend effect coding produced this from "true" placeholder
                "goal_present[true]": jnp.array([1.0]),
            }
        )

        result = zero_unimplemented_features(
            state, filled, param_implementation=sample_param_implementation
        )

        # Should be zeroed because scenario_B doesn't implement goal_present
        assert np.array(result.features["goal_present[true]"])[0] == 0.0
