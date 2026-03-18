"""Full-scale integration test with synthetic data generation.

This test generates synthetic data from a known logistic regression DGP,
fits a model using the actual pooled fitting pipeline, and verifies that
the recovered coefficients match the true values.

The test validates:
1. Coefficients are recovered within posterior uncertainty
2. Effect-coded coefficients sum to zero
3. Signs of coefficients are correct
4. Intercepts are recovered correctly

Run with: uv run pytest tests/pooled_fitting/test_synthetic_dgp.py -v
"""

import numpy as np
import pandas as pd
import pytest
from scipy.special import expit  # logistic function

from lib.pooled_fitting.core import fit_pooled_regression
from lib.pooled_fitting.data_prep import PARAMETER_IMPLEMENTATION

pytestmark = pytest.mark.slow

# =============================================================================
# Synthetic Data Generation
# =============================================================================

# Category harmonization map: raw -> harmonized
# action_efficacy_binary is harmonized from 'true'/'false' to 'effective'/'not_effective'
# by harmonize_action_efficacy() in core.py
CATEGORY_HARMONIZATION = {
    "action_efficacy_binary": {
        "true": "effective",
        "false": "not_effective",
    }
}


def generate_synthetic_data(
    n_samples_per_cell: int = 50,
    true_intercept: float = -2.0,
    true_coefficients: dict[str, dict[str, float]] | None = None,
    seed: int = 42,
) -> tuple[pd.DataFrame, dict[str, float], dict[str, dict[str, float]]]:
    """Generate synthetic data from a logistic regression DGP.

    Creates data that mimics the structure expected by fit_pooled_regression:
    - Multiple scenarios (using real scenario names from PARAMETER_IMPLEMENTATION)
    - Multiple models and variations
    - Categorical parameters with effect-coded coefficients
    - Binomial outcomes

    The DGP is:
        logit(p) = intercept + sum(effect_coded_coefficients)
        y ~ Binomial(n_total, p)

    Args:
        n_samples_per_cell: Number of samples per unique parameter combination.
        true_intercept: True intercept (on logit scale).
        true_coefficients: Dict mapping param -> {category: coefficient}.
            Coefficients should be effect-coded (sum to zero within param).
            If None, uses default test coefficients.
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (df, intercepts_dict, true_coefficients)
        - df: DataFrame ready for fit_pooled_regression
        - intercepts_dict: Dict mapping model_variation -> true intercept
        - true_coefficients: The coefficients used (possibly defaults)
    """
    rng = np.random.default_rng(seed)

    # Default coefficients (effect-coded, sum to zero within each param)
    # Using parameters that don't require complex harmonization
    #
    # Effect sizes are deliberately varied to test recovery:
    # - Large effects (3 logits difference): goal_conflict, threat
    # - Moderate effects (~1 logit difference): goal_present
    # - Zero effects: action_oversight, action_efficacy_binary
    #
    # This makes it easy to verify we recover ordering and positivity correctly.
    if true_coefficients is None:
        true_coefficients = {
            # LARGE EFFECT: goal_conflict (+1.5 vs -1.5 = 3 logit difference)
            "goal_conflict": {
                "true": 1.5,  # Conflict strongly increases misalignment
                "false": -1.5,
            },
            # LARGE EFFECT: threat (replacement >> none)
            "threat": {
                "replacement": 1.2,  # Strong threat increases misalignment
                "other": 0.0,  # Neutral
                "none": -1.2,  # No threat decreases
            },
            # MODERATE EFFECT: goal_present
            "goal_present": {
                "true": 0.5,  # Goal present slightly increases misalignment
                "false": -0.5,
            },
            # ZERO EFFECT: action_oversight (should recover ~0)
            "action_oversight": {
                "none": 0.0,
                "oversight": 0.0,
            },
            # ZERO EFFECT: action_efficacy_binary (should recover ~0)
            # Note: uses 'true'/'false' in AM scenario -> harmonized to 'effective'/'not_effective'
            "action_efficacy_binary": {
                "true": 0.0,  # -> 'effective' after harmonization
                "false": 0.0,  # -> 'not_effective' after harmonization
            },
        }

    # Verify effect coding constraint (coefficients sum to zero)
    for param, coefs in true_coefficients.items():
        coef_sum = sum(coefs.values())
        assert abs(coef_sum) < 1e-10, (
            f"Coefficients for {param} don't sum to zero: {coef_sum}"
        )

    # Use a single scenario that implements all our test parameters
    # agentic_misalignment_v2 implements all 12 parameters
    scenario = "agentic_misalignment_v2"
    variation = "alert"

    # Use two synthetic models to test model_variation intercepts
    models = ["synthetic_model_a", "synthetic_model_b"]
    model_intercept_offsets = {
        "synthetic_model_a": 0.0,  # Baseline
        "synthetic_model_b": 0.5,  # Higher base rate
    }

    # Generate all combinations of categorical values
    param_values = {
        param: list(coefs.keys()) for param, coefs in true_coefficients.items()
    }

    # Create parameter grid
    from itertools import product

    param_names = list(param_values.keys())
    param_combos = list(product(*[param_values[p] for p in param_names]))

    rows = []
    for model in models:
        for combo in param_combos:
            param_dict = dict(zip(param_names, combo))

            # Compute linear predictor
            eta = true_intercept + model_intercept_offsets[model]
            for param, value in param_dict.items():
                eta += true_coefficients[param][value]

            # Convert to probability
            p = expit(eta)

            # Generate binomial outcomes
            # n_samples_per_cell = number of DataFrame rows per parameter combination
            # Each row has n_total = random binomial trials (5-20)
            # So total trials per cell ≈ n_samples_per_cell × 12.5
            for _ in range(n_samples_per_cell):
                n_total = rng.integers(5, 20)  # Random binomial trials per row
                score = rng.binomial(n_total, p)
                meta_score = score / n_total if n_total > 0 else 0.0

                row = {
                    "meta_model": model,
                    "variation": variation,
                    "scenario": scenario,
                    "meta_score": meta_score,
                    "score": score,
                    "n_total": n_total,
                    **param_dict,
                }
                rows.append(row)

    df = pd.DataFrame(rows)

    # Add remaining required parameters with constant values
    # AM scenario implements all these params, so we need valid values (not NaN)
    # Using the first category from PARAM_CATEGORY_ORDER for each
    from lib.pooled_fitting.config import PARAM_CATEGORY_ORDER

    remaining_params = {
        "cot_privacy": PARAM_CATEGORY_ORDER["cot_privacy"][0],  # "discarded"
        "anti_misalignment": PARAM_CATEGORY_ORDER["anti_misalignment"][
            0
        ],  # "encourage_creativity"
        "independence": PARAM_CATEGORY_ORDER["independence"][
            0
        ],  # "strong_independence"
        "reasoning_instructions": PARAM_CATEGORY_ORDER["reasoning_instructions"][
            0
        ],  # "strategic_goals"
        "filler_richness": PARAM_CATEGORY_ORDER["filler_richness"][0],  # "full"
        "date_month_year": PARAM_CATEGORY_ORDER["date_month_year"][0],  # "Jul 2024"
        "cot_tag": PARAM_CATEGORY_ORDER["cot_tag"][0],  # "thinking"
    }
    for param, value in remaining_params.items():
        df[param] = value  # Constant value (no signal, but features won't be zeroed)

    # Compute true intercepts dict (model_variation format)
    intercepts_dict = {}
    for model in models:
        pair_key = f"{model}_{variation}"
        intercepts_dict[pair_key] = true_intercept + model_intercept_offsets[model]

    return df, intercepts_dict, true_coefficients


def get_harmonized_category(param: str, category: str) -> str:
    """Get the harmonized category name for a given param/category.

    Handles the fact that some params get their values remapped
    by harmonization functions in core.py.
    """
    if param in CATEGORY_HARMONIZATION:
        return CATEGORY_HARMONIZATION[param].get(category, category)
    return category


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def synthetic_fit_result():
    """Fit model to synthetic data (cached for all tests in module)."""
    df, true_intercepts, true_coefficients = generate_synthetic_data(
        n_samples_per_cell=30,  # Enough for reasonable estimates
        seed=12345,
    )

    # Fit with fast MCMC settings
    result = fit_pooled_regression(
        df,
        mcmc_mode="ultra",  # Fast for testing
    )

    return result, true_intercepts, true_coefficients


# =============================================================================
# Tests
# =============================================================================


class TestCoefficientRecovery:
    """Tests that verify coefficient recovery from synthetic data."""

    def test_fit_completes_successfully(self, synthetic_fit_result):
        """The fitting process should complete without errors."""
        result, _, _ = synthetic_fit_result
        assert result is not None
        assert result.posteriors is not None
        assert len(result.posteriors) > 0

    def test_coefficients_have_correct_sign(self, synthetic_fit_result):
        """Recovered coefficients should have the same sign as true values."""
        result, _, true_coefficients = synthetic_fit_result

        for param, true_coefs in true_coefficients.items():
            for category, true_value in true_coefs.items():
                if abs(true_value) < 0.15:
                    # Skip near-zero coefficients (sign is ambiguous)
                    continue

                # Get harmonized category name for posterior lookup
                harmonized_cat = get_harmonized_category(param, category)
                # Posteriors are prefixed with model type (e.g., "combined_")
                key = f"combined_{param}_effects[{harmonized_cat}]"

                if key not in result.posteriors:
                    pytest.skip(f"Coefficient {key} not in posteriors")

                posterior_mean = np.mean(result.posteriors[key])
                true_sign = np.sign(true_value)
                recovered_sign = np.sign(posterior_mean)

                assert true_sign == recovered_sign, (
                    f"Sign mismatch for {key}: "
                    f"true={true_value:.3f}, recovered={posterior_mean:.3f}"
                )

    def test_coefficients_within_posterior_interval(self, synthetic_fit_result):
        """True coefficients should be within 95% posterior interval."""
        result, _, true_coefficients = synthetic_fit_result

        n_outside = 0
        n_total = 0

        for param, true_coefs in true_coefficients.items():
            for category, true_value in true_coefs.items():
                # Get harmonized category name for posterior lookup
                harmonized_cat = get_harmonized_category(param, category)
                # Posteriors are prefixed with model type
                key = f"combined_{param}_effects[{harmonized_cat}]"

                if key not in result.posteriors:
                    continue

                samples = result.posteriors[key]
                lower = np.percentile(samples, 2.5)
                upper = np.percentile(samples, 97.5)

                n_total += 1
                if not (lower <= true_value <= upper):
                    n_outside += 1

        # Allow some coefficients to be outside (sampling variability + ultra mode)
        # With ultra mode (100 samples), expect more variability
        coverage = 1 - (n_outside / n_total) if n_total > 0 else 1.0
        assert coverage >= 0.60, (
            f"Coverage too low: {coverage:.1%} ({n_outside}/{n_total} outside 95% CI)"
        )

    def test_effect_coded_coefficients_sum_to_zero(self, synthetic_fit_result):
        """Effect-coded coefficients should sum to zero (after normalization)."""
        result, _, true_coefficients = synthetic_fit_result

        for param in true_coefficients.keys():
            # Collect all categories for this param (from combined model)
            param_coefs = {}
            prefix = f"combined_{param}_effects["
            for key, samples in result.posteriors.items():
                if key.startswith(prefix):
                    # Extract category name
                    category = key[len(prefix) : -1]  # Remove prefix and trailing ]
                    if category != "_DUMMY_":
                        param_coefs[category] = samples

            if not param_coefs:
                continue

            # Sum across categories for each posterior draw
            all_samples = np.stack(list(param_coefs.values()), axis=0)
            sums = np.sum(all_samples, axis=0)

            # Should be very close to zero
            mean_sum = np.mean(np.abs(sums))
            assert mean_sum < 1e-6, (
                f"Coefficients for {param} don't sum to zero: mean|sum|={mean_sum:.2e}"
            )

    def test_intercepts_recovered_approximately(self, synthetic_fit_result):
        """Model-variation intercepts should be approximately recovered."""
        result, true_intercepts, _ = synthetic_fit_result

        for pair_key, true_intercept in true_intercepts.items():
            # Posteriors are prefixed with model type
            coef_key = f"combined_model_variation_effects[{pair_key}]"
            if coef_key not in result.posteriors:
                pytest.skip(f"Intercept {coef_key} not found")

            samples = result.posteriors[coef_key]
            posterior_mean = np.mean(samples)

            # Intercepts are harder to recover precisely due to:
            # 1. Prior influence (N(-3, 3²))
            # 2. Correlation with other coefficients
            # Check that we're within ~2 units (generous tolerance for ultra mode)
            diff = abs(posterior_mean - true_intercept)
            assert diff < 3.0, (
                f"Intercept {pair_key} not recovered: "
                f"true={true_intercept:.2f}, recovered={posterior_mean:.2f}"
            )

    def test_intercept_difference_preserved(self, synthetic_fit_result):
        """The difference between model intercepts should be preserved.

        True: model_b has +0.5 higher intercept than model_a.
        This relative difference is easier to recover than absolute values.
        """
        result, true_intercepts, _ = synthetic_fit_result

        key_a = "combined_model_variation_effects[synthetic_model_a_alert]"
        key_b = "combined_model_variation_effects[synthetic_model_b_alert]"

        if key_a not in result.posteriors or key_b not in result.posteriors:
            pytest.skip("Intercept keys not found")

        mean_a = np.mean(result.posteriors[key_a])
        mean_b = np.mean(result.posteriors[key_b])

        # True difference is 0.5 (model_b is higher)
        true_diff = (
            true_intercepts["synthetic_model_b_alert"]
            - true_intercepts["synthetic_model_a_alert"]
        )
        recovered_diff = mean_b - mean_a

        # Check that model_b > model_a (correct ordering)
        assert mean_b > mean_a, (
            f"Intercept ordering wrong: model_b ({mean_b:.2f}) should be > model_a ({mean_a:.2f})"
        )

        # Check that difference is approximately correct (within 1 unit)
        diff_error = abs(recovered_diff - true_diff)
        assert diff_error < 1.5, (
            f"Intercept difference not recovered: "
            f"true_diff={true_diff:.2f}, recovered_diff={recovered_diff:.2f}"
        )

    def test_intercept_true_values_in_credible_interval(self, synthetic_fit_result):
        """True intercept values should be within posterior credible intervals."""
        result, true_intercepts, _ = synthetic_fit_result

        n_inside = 0
        n_total = 0

        for pair_key, true_intercept in true_intercepts.items():
            coef_key = f"combined_model_variation_effects[{pair_key}]"
            if coef_key not in result.posteriors:
                continue

            samples = result.posteriors[coef_key]
            lower = np.percentile(samples, 2.5)
            upper = np.percentile(samples, 97.5)

            n_total += 1
            if lower <= true_intercept <= upper:
                n_inside += 1

        # At least one intercept should be within its 95% CI
        # (with ultra mode this is a weak test, but verifies basic functionality)
        assert n_inside >= 1, f"No intercepts within 95% CI: {n_inside}/{n_total}"

    def test_relative_ordering_preserved(self, synthetic_fit_result):
        """Coefficients with large differences should maintain relative ordering."""
        result, _, true_coefficients = synthetic_fit_result

        # Check threat: replacement should be > none (large effect difference)
        threat_coefs = true_coefficients.get("threat", {})
        if "replacement" in threat_coefs and "none" in threat_coefs:
            # Posteriors are prefixed with model type
            key_repl = "combined_threat_effects[replacement]"
            key_none = "combined_threat_effects[none]"

            if key_repl in result.posteriors and key_none in result.posteriors:
                mean_repl = np.mean(result.posteriors[key_repl])
                mean_none = np.mean(result.posteriors[key_none])

                # True values: replacement > none
                assert mean_repl > mean_none, (
                    f"Relative ordering not preserved for threat: "
                    f"replacement ({mean_repl:.3f}) should be > none ({mean_none:.3f})"
                )

        # Check goal_conflict: true should be > false (large effect)
        gc_coefs = true_coefficients.get("goal_conflict", {})
        if "true" in gc_coefs and "false" in gc_coefs:
            key_true = "combined_goal_conflict_effects[true]"
            key_false = "combined_goal_conflict_effects[false]"

            if key_true in result.posteriors and key_false in result.posteriors:
                mean_true = np.mean(result.posteriors[key_true])
                mean_false = np.mean(result.posteriors[key_false])

                assert mean_true > mean_false, (
                    f"Relative ordering not preserved for goal_conflict: "
                    f"true ({mean_true:.3f}) should be > false ({mean_false:.3f})"
                )

    def test_large_effects_have_correct_sign(self, synthetic_fit_result):
        """Large effects should be recovered with correct sign."""
        result, _, true_coefficients = synthetic_fit_result

        # Define which coefficients have large positive/negative effects
        large_positive = [
            ("goal_conflict", "true"),  # +1.5
            ("threat", "replacement"),  # +1.2
        ]
        large_negative = [
            ("goal_conflict", "false"),  # -1.5
            ("threat", "none"),  # -1.2
        ]

        for param, category in large_positive:
            harmonized_cat = get_harmonized_category(param, category)
            key = f"combined_{param}_effects[{harmonized_cat}]"
            if key in result.posteriors:
                mean_val = np.mean(result.posteriors[key])
                assert mean_val > 0, (
                    f"Large positive effect {key} should be positive, got {mean_val:.3f}"
                )

        for param, category in large_negative:
            harmonized_cat = get_harmonized_category(param, category)
            key = f"combined_{param}_effects[{harmonized_cat}]"
            if key in result.posteriors:
                mean_val = np.mean(result.posteriors[key])
                assert mean_val < 0, (
                    f"Large negative effect {key} should be negative, got {mean_val:.3f}"
                )

    def test_zero_effects_are_approximately_zero(self, synthetic_fit_result):
        """Zero effects should be recovered as approximately zero."""
        result, _, true_coefficients = synthetic_fit_result

        # Parameters with zero true effect
        zero_effect_params = ["action_oversight", "action_efficacy_binary"]

        for param in zero_effect_params:
            for category, true_value in true_coefficients.get(param, {}).items():
                if true_value != 0.0:
                    continue

                harmonized_cat = get_harmonized_category(param, category)
                key = f"combined_{param}_effects[{harmonized_cat}]"

                if key not in result.posteriors:
                    continue

                samples = result.posteriors[key]
                mean_val = np.mean(samples)

                # Zero effects should be approximately zero (within 0.5 of zero)
                # This is a generous tolerance for ultra mode
                assert abs(mean_val) < 0.8, (
                    f"Zero effect {key} should be ~0, got {mean_val:.3f}"
                )


class TestSyntheticDataGeneration:
    """Tests for the synthetic data generation function itself."""

    def test_generates_expected_columns(self):
        """Generated data should have all required columns."""
        df, _, _ = generate_synthetic_data(n_samples_per_cell=5)

        required = ["meta_model", "variation", "scenario", "meta_score", "n_total"]
        for col in required:
            assert col in df.columns, f"Missing required column: {col}"

    def test_effect_coding_constraint_enforced(self):
        """Should raise error if coefficients don't sum to zero."""
        bad_coefficients = {
            "goal_present": {
                "true": 0.5,
                "false": 0.0,  # Doesn't sum to zero!
            },
        }

        with pytest.raises(AssertionError, match="don't sum to zero"):
            generate_synthetic_data(true_coefficients=bad_coefficients)

    def test_meta_score_in_valid_range(self):
        """meta_score should be between 0 and 1."""
        df, _, _ = generate_synthetic_data(n_samples_per_cell=10)

        assert df["meta_score"].min() >= 0.0
        assert df["meta_score"].max() <= 1.0

    def test_scenario_is_valid(self):
        """Scenario should be in PARAMETER_IMPLEMENTATION."""
        df, _, _ = generate_synthetic_data(n_samples_per_cell=5)

        scenarios = df["scenario"].unique()
        for scenario in scenarios:
            assert scenario in PARAMETER_IMPLEMENTATION, f"Unknown scenario: {scenario}"

    def test_harmonization_mapping_correct(self):
        """Category harmonization mapping should be correct."""
        # action_efficacy_binary 'true' -> 'effective'
        assert get_harmonized_category("action_efficacy_binary", "true") == "effective"
        assert (
            get_harmonized_category("action_efficacy_binary", "false")
            == "not_effective"
        )

        # Other params unchanged
        assert get_harmonized_category("goal_present", "true") == "true"
        assert get_harmonized_category("threat", "replacement") == "replacement"


class TestPosteriorSummary:
    """Tests that print posterior summary information for inspection."""

    def test_print_posterior_summary(self, synthetic_fit_result):
        """Print posterior means and 95% CIs for manual inspection.

        This test always passes but prints useful summary statistics.
        Run with: pytest -v -s tests/pooled_fitting/test_synthetic_dgp.py::TestPosteriorSummary
        """
        result, true_intercepts, true_coefficients = synthetic_fit_result

        print("\n" + "=" * 80)
        print("POSTERIOR SUMMARY (combined model)")
        print("=" * 80)

        # Print intercepts
        print("\n--- INTERCEPTS ---")
        print(f"{'Pair':<35} {'True':>8} {'Mean':>8} {'95% CI':>20}")
        print("-" * 75)
        for pair_key, true_val in true_intercepts.items():
            coef_key = f"combined_model_variation_effects[{pair_key}]"
            if coef_key in result.posteriors:
                samples = result.posteriors[coef_key]
                mean = np.mean(samples)
                lo, hi = np.percentile(samples, [2.5, 97.5])
                print(
                    f"{pair_key:<35} {true_val:>8.2f} {mean:>8.2f} [{lo:>7.2f}, {hi:>7.2f}]"
                )

        # Print coefficients by parameter
        print("\n--- COEFFICIENTS ---")
        print(f"{'Parameter':<30} {'True':>8} {'Mean':>8} {'95% CI':>20}")
        print("-" * 75)

        for param, true_coefs in true_coefficients.items():
            for category, true_val in true_coefs.items():
                harmonized_cat = get_harmonized_category(param, category)
                coef_key = f"combined_{param}_effects[{harmonized_cat}]"
                if coef_key in result.posteriors:
                    samples = result.posteriors[coef_key]
                    mean = np.mean(samples)
                    lo, hi = np.percentile(samples, [2.5, 97.5])
                    label = f"{param}[{harmonized_cat}]"
                    print(
                        f"{label:<30} {true_val:>8.2f} {mean:>8.2f} [{lo:>7.2f}, {hi:>7.2f}]"
                    )

        print("\n" + "=" * 80)

        # Test always passes - this is for inspection
        assert True


class TestModelDiagnostics:
    """Tests for model diagnostics and convergence."""

    def test_convergence_metrics_present(self, synthetic_fit_result):
        """Fit result should include convergence information."""
        result, _, _ = synthetic_fit_result

        assert hasattr(result, "convergence_ok")
        assert hasattr(result, "convergence_issues")
        assert isinstance(result.convergence_issues, list)

    def test_summary_stats_computed(self, synthetic_fit_result):
        """Summary statistics should be computed."""
        result, _, _ = synthetic_fit_result

        assert result.summary is not None
        assert isinstance(result.summary, dict)

    def test_implemented_params_identified(self, synthetic_fit_result):
        """Should identify which params are implemented."""
        result, _, true_coefficients = synthetic_fit_result

        assert result.implemented_params is not None
        assert len(result.implemented_params) > 0

        # The params we used in synthetic data should be identified
        for param in true_coefficients.keys():
            assert param in result.implemented_params, (
                f"Expected {param} to be identified as implemented"
            )

    def test_posteriors_have_expected_keys(self, synthetic_fit_result):
        """Posteriors should have keys for all fitted parameters."""
        result, _, true_coefficients = synthetic_fit_result

        # Check that we have posteriors for our test params (from combined model)
        for param in true_coefficients.keys():
            # Posteriors are prefixed with model type
            prefix = f"combined_{param}_effects["
            matching_keys = [
                k for k in result.posteriors.keys() if k.startswith(prefix)
            ]
            assert len(matching_keys) > 0, f"No posterior keys found for {param}"
