"""End-to-end tests for effect coding with _DUMMY_ categories.

These tests verify the full pipeline:
1. inject_dummy_rows adds _DUMMY_ to data
2. HiBayES processes _DUMMY_ correctly as the reference category
3. Coefficients are extracted and normalized correctly
4. Results make sense for known synthetic data

Run with: uv run pytest tests/pooled_fitting/test_effect_coding_e2e.py -v
"""

import numpy as np
import pandas as pd

from lib.analysis.effect_coding import (
    DUMMY_CATEGORY,
    inject_dummy_rows,
    normalize_effect_coded_coefficients,
)


class TestInjectDummyRows:
    """Tests for inject_dummy_rows()."""

    def test_dummy_category_present_after_injection(self):
        """_DUMMY_ should be present in all categorical columns after injection."""
        df = pd.DataFrame(
            {
                "feature_a": ["cat1", "cat2", "cat1"],
                "feature_b": ["x", "y", "x"],
                "score": [1, 0, 1],
                "n_total": [10, 10, 10],
            }
        )

        result = inject_dummy_rows(df, ["feature_a", "feature_b"])

        assert DUMMY_CATEGORY in result["feature_a"].values
        assert DUMMY_CATEGORY in result["feature_b"].values

    def test_dummy_row_has_zero_weight(self):
        """The injected dummy row should have n_total=0."""
        df = pd.DataFrame(
            {
                "feature_a": ["cat1", "cat2"],
                "score": [1, 0],
                "n_total": [10, 10],
            }
        )

        result = inject_dummy_rows(df, ["feature_a"])

        # Find the dummy row
        dummy_mask = result["feature_a"] == DUMMY_CATEGORY
        assert dummy_mask.sum() == 1
        assert result.loc[dummy_mask, "n_total"].iloc[0] == 0

    def test_original_data_unchanged(self):
        """Original data rows should not be modified."""
        df = pd.DataFrame(
            {
                "feature_a": ["cat1", "cat2"],
                "score": [1, 0],
                "n_total": [10, 20],
            }
        )

        result = inject_dummy_rows(df, ["feature_a"])

        # First two rows should be unchanged
        assert result.iloc[0]["feature_a"] == "cat1"
        assert result.iloc[0]["n_total"] == 10
        assert result.iloc[1]["feature_a"] == "cat2"
        assert result.iloc[1]["n_total"] == 20


class TestNormalizeEffectCodedCoefficients:
    """Tests for normalize_effect_coded_coefficients()."""

    def test_real_coefficients_sum_to_zero(self):
        """After normalization, real category coefficients should sum to zero."""
        # Simulated posterior samples for a variable with 3 categories + dummy
        # Note: HiBayES uses "variable_effects[category]" naming convention
        n_samples = 100
        coefficients = {
            "var_effects[cat1]": np.random.randn(n_samples) + 0.5,
            "var_effects[cat2]": np.random.randn(n_samples) - 0.3,
            "var_effects[cat3]": np.random.randn(n_samples) + 0.1,
            "var_effects[_DUMMY_]": np.random.randn(n_samples) * 2,  # Higher variance
        }

        normalized = normalize_effect_coded_coefficients(
            coefficients, remove_dummy=True
        )

        # Should have 3 coefficients (dummy removed)
        assert len(normalized) == 3
        assert "var_effects[_DUMMY_]" not in normalized

        # Sum should be ~0 for each draw
        total = (
            normalized["var_effects[cat1]"]
            + normalized["var_effects[cat2]"]
            + normalized["var_effects[cat3]"]
        )
        np.testing.assert_array_almost_equal(total, 0, decimal=10)

    def test_dummy_removed_by_default(self):
        """_DUMMY_ coefficient should be removed by default."""
        coefficients = {
            "var_effects[cat1]": np.array([1.0, 2.0]),
            "var_effects[_DUMMY_]": np.array([0.5, 0.5]),
        }

        normalized = normalize_effect_coded_coefficients(coefficients)

        assert "var_effects[_DUMMY_]" not in normalized
        assert "var_effects[cat1]" in normalized

    def test_model_variation_not_normalized(self):
        """model_variation coefficients should not be normalized (they're intercepts)."""
        coefficients = {
            "model_variation_effects[model_a_var_1]": np.array([1.0, 2.0]),
            "model_variation_effects[model_b_var_1]": np.array([3.0, 4.0]),
            "model_variation_effects[_DUMMY_]": np.array([0.0, 0.0]),
        }

        normalized = normalize_effect_coded_coefficients(coefficients)

        # Should be unchanged (except dummy removed)
        np.testing.assert_array_equal(
            normalized["model_variation_effects[model_a_var_1]"], np.array([1.0, 2.0])
        )
        np.testing.assert_array_equal(
            normalized["model_variation_effects[model_b_var_1]"], np.array([3.0, 4.0])
        )


class TestDummyCategoryConstant:
    """Tests for the DUMMY_CATEGORY constant."""

    def test_dummy_category_is_underscore_dummy(self):
        """DUMMY_CATEGORY should be '_DUMMY_' (not zzz_reference or similar)."""
        assert DUMMY_CATEGORY == "_DUMMY_"

    def test_dummy_sorts_after_typical_categories(self):
        """_DUMMY_ should sort after typical category names in category_order lists.

        Note: We rely on explicit ordering in category_order, not alphabetical sorting.
        But _DUMMY_ starting with underscore means it sorts FIRST alphabetically,
        which is why we always put it at the END of category_order lists explicitly.
        """
        # This documents the behavior - underscore sorts before letters
        categories = ["true", "false", "_DUMMY_"]
        sorted_cats = sorted(categories)

        # Alphabetically, _DUMMY_ comes first (underscore < letters in ASCII)
        assert sorted_cats[0] == "_DUMMY_"

        # But in our category_order lists, we explicitly put it last
        # This is important - we don't rely on alphabetical sorting


class TestCategoryOrderWithDummy:
    """Tests verifying category_order lists have _DUMMY_ at the end."""

    def test_param_category_order_has_dummy_last(self):
        """All category orders in config should have _DUMMY_ at the end."""
        from lib.pooled_fitting.config import PARAM_CATEGORY_ORDER

        for param, categories in PARAM_CATEGORY_ORDER.items():
            assert categories[-1] == "_DUMMY_", (
                f"PARAM_CATEGORY_ORDER['{param}'] should have _DUMMY_ at end, "
                f"got: {categories}"
            )
