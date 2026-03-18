#!/usr/bin/env python3
"""Compute optimal sample allocation across (model, variation) pairs.

Maximizes value based on precision of odds ratio estimation, subject to budget constraint.

The value function is based on the standard error of log-odds, which determines
how precisely we can estimate effect sizes (odds ratios) of ablations:
- SE(log odds) = 1 / sqrt(n * p * (1-p))
- Multiplicative error = exp(SE)

Value saturates once precision is "good enough" (around 1.2x error).

Usage:
    uv run python scripts/compute_sample_allocation.py
    uv run python scripts/compute_sample_allocation.py --budget 50000
    uv run python scripts/compute_sample_allocation.py --format csv
    uv run python scripts/compute_sample_allocation.py --output configs/final_sample_targets.json
"""

import argparse
import json
import logging
import os
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
import numpy as np
from scipy.optimize import minimize

from lib.model_registry import MODEL_REGISTRY, s3_name_to_api_name

# Path to configs
CONFIGS_DIR = Path(__file__).parent.parent / "configs"
SAMPLE_TARGETS_PATH = CONFIGS_DIR / "sample_targets.json"
TOKEN_ESTIMATES_PATH = CONFIGS_DIR / "token_estimates.json"


def load_token_estimates() -> dict[str, dict[str, dict[str, int]]]:
    """Load token estimates from JSON file."""
    if not TOKEN_ESTIMATES_PATH.exists():
        raise FileNotFoundError(f"Token estimates not found at {TOKEN_ESTIMATES_PATH}")

    with open(TOKEN_ESTIMATES_PATH) as f:
        data = json.load(f)

    return data.get("token_estimates", {})


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def format_significant(n: float, sig_figs: int = 2) -> str:
    """Format number to N significant figures for display."""
    if n == 0:
        return "0"
    from math import floor, log10

    magnitude = floor(log10(abs(n)))
    if magnitude >= 6:
        # Use M for millions
        return f"{n / 1e6:.{sig_figs - 1}f}M"
    elif magnitude >= 3:
        # Use K for thousands
        return f"{n / 1e3:.{sig_figs - 1}f}K"
    else:
        return f"{n:.0f}"


# Value function for odds ratio (effect size) precision estimation
#
# For comparing ablations with ~50/50 split, the 20:1 likelihood ratio interval
# on the odds ratio has multiplicative error:
#
#   mult_error ≈ exp(4.9 / sqrt(n * p * (1-p)))
#
# where:
#   - n = total samples in the bucket
#   - p = misalignment rate
#   - 4.9 = 2 * sqrt(2 * log(20)) ≈ 2 * 2.45 (factor of 2 for comparing two groups)
#
# User-specified value curve based on multiplicative error:
# - 1.01x error: 100% value (excellent precision)
# - 1.2x error: 90% value (good precision)
# - 1.5x error: 60% value (moderate precision)
# - 2x error: 30% value (poor precision)
# - 4x error: 10% value (very poor)
# - 8x error: 0% value (uninformative)
MULT_ERROR_POINTS = np.array([1.0, 1.01, 1.2, 1.5, 2.0, 4.0, 8.0, 1000.0])
VALUE_POINTS = np.array([1.0, 1.0, 0.9, 0.6, 0.3, 0.1, 0.0, 0.0])


def odds_ratio_value(n: float, p: float) -> float:
    """Compute value based on precision of odds ratio (effect size) estimation.

    Uses the 20:1 likelihood ratio interval for comparing ablations.
    Assumes ~50/50 split across ablation conditions.

    Args:
        n: Total number of samples in the bucket
        p: Posterior probability of misalignment

    Returns:
        Value in [0, 1] based on achievable precision on effect sizes
    """
    # For 50/50 split comparing two conditions:
    # SE(log OR) ≈ 2 / sqrt(n * p * (1-p))
    # 20:1 LR multiplicative error ≈ exp(2.45 * SE) = exp(4.9 / sqrt(n * p * (1-p)))
    npq = max(n * p * (1 - p), 1e-10)
    mult_error = np.exp(4.9 / np.sqrt(npq))

    # Interpolate value from the specified curve
    return float(np.interp(mult_error, MULT_ERROR_POINTS, VALUE_POINTS))


# Variation -> Scenario mapping
VARIATION_TO_SCENARIO = {
    "agentic_misalignment_v2/alert": "agentic_misalignment_v2",
    "agentic_misalignment_v2/leak-starsentinel": "agentic_misalignment_v2",
    "agentic_misalignment_v2/leak-doj": "agentic_misalignment_v2",
    "email_spam_filter_v2/email_spam_filter": "email_spam_filter_v2",
    "gpu_decision_email_assistant/gpu_decision": "gpu_decision_email_assistant",
    "hiding_reward_hacking/hiding_reward_hacking": "hiding_reward_hacking",
    "power_preservation/threat": "power_preservation",
    "power_preservation/enhancement": "power_preservation",
    "power_preservation/expansion": "power_preservation",
    "sem_v2/classification": "sem_v2",
    "sem_v2/summarization": "sem_v2",
}

# All variations we care about
VARIATIONS = list(VARIATION_TO_SCENARIO.keys())


@dataclass
class BucketData:
    """Data for a (model, variation) bucket."""

    model: str
    variation: str
    current_samples: int
    misaligned_count: int
    cost_per_sample: float  # USD
    input_tokens: int  # Per sample
    output_tokens: int  # Per sample

    @property
    def misalignment_rate(self) -> float:
        if self.current_samples == 0:
            return 0.0
        return self.misaligned_count / self.current_samples

    @property
    def posterior_rate(self) -> float:
        """Posterior estimate using Beta(1,9) prior."""
        return (self.misaligned_count + 1) / (self.current_samples + 10)

    @property
    def has_misalignment(self) -> bool:
        return self.misaligned_count > 0


def load_listing() -> dict[str, Any]:
    """Load listing.json from S3."""
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        raise ValueError("S3_BUCKET not set")

    s3_root = os.environ.get("PROPENSITY_S3_ROOT", "propensity")
    s3 = boto3.client("s3")
    key = f"{s3_root}/evals/logs/listing.json"

    logger.info(f"Loading listing.json from s3://{bucket}/{key}...")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read())


def load_disabled_models() -> set[str]:
    """Load models that are disabled (all zeros) in sample_targets.json."""
    if not SAMPLE_TARGETS_PATH.exists():
        logger.warning(f"sample_targets.json not found at {SAMPLE_TARGETS_PATH}")
        return set()

    with open(SAMPLE_TARGETS_PATH) as f:
        data = json.load(f)

    disabled = set()
    for model, variations in data.get("targets", {}).items():
        # Model is disabled if all variations are 0
        if all(v == 0 for v in variations.values()):
            disabled.add(model)

    if disabled:
        logger.info(f"Disabled models (from sample_targets.json): {len(disabled)}")
        for m in sorted(disabled):
            logger.info(f"  - {m}")

    return disabled


def get_model_costs() -> dict[str, tuple[float, float]]:
    """Get (input_cost, output_cost) per 1M tokens for each model API name."""
    costs = {}
    for model in MODEL_REGISTRY:
        if model.input_cost is not None and model.output_cost is not None:
            costs[model.api_name] = (model.input_cost, model.output_cost)
    return costs


def compute_sample_cost(
    model_api_name: str,
    variation: str,
    model_costs: dict[str, tuple[float, float]],
    token_estimates: dict[str, dict[str, dict[str, int]]],
) -> tuple[float, int, int] | None:
    """Compute cost per sample in USD for a (model, variation) pair.

    Returns:
        Tuple of (cost_per_sample, input_tokens, output_tokens) or None if not found.
    """
    if model_api_name not in model_costs:
        return None

    # Get token estimate for this specific (model, variation) pair
    if model_api_name in token_estimates:
        model_tokens = token_estimates[model_api_name]
        if variation in model_tokens:
            input_tokens = model_tokens[variation]["input_tokens"]
            output_tokens = model_tokens[variation]["output_tokens"]
        else:
            return None
    else:
        return None

    input_cost_per_m, output_cost_per_m = model_costs[model_api_name]

    cost = (input_tokens * input_cost_per_m / 1_000_000) + (
        output_tokens * output_cost_per_m / 1_000_000
    )
    return cost, input_tokens, output_tokens


def collect_bucket_data(listing: dict[str, Any]) -> list[BucketData]:
    """Collect data for all (model, variation) buckets."""
    model_costs = get_model_costs()
    token_estimates = load_token_estimates()

    # Aggregate: (model, variation) -> (misaligned, total)
    aggregated: dict[tuple[str, str], tuple[int, int]] = defaultdict(lambda: (0, 0))

    for path, entry in listing.items():
        parts = path.split("/")
        if len(parts) < 4:
            continue

        scenario = parts[0]
        variation = parts[1]
        variation_key = f"{scenario}/{variation}"

        if variation_key not in VARIATIONS:
            continue
        if "entropy" in path:
            continue
        if entry.get("status") != "success":
            continue

        model_s3 = entry.get("model", "unknown")
        model_api = s3_name_to_api_name(model_s3)

        primary_metric = entry.get("primary_metric", {})
        score = primary_metric.get("value")

        if score is not None:
            key = (model_api, variation_key)
            mis, tot = aggregated[key]
            aggregated[key] = (mis + int(score), tot + 1)

    # Convert to BucketData objects
    buckets = []
    for (model_api, variation_key), (mis, tot) in aggregated.items():
        result = compute_sample_cost(
            model_api, variation_key, model_costs, token_estimates
        )
        if result is None:
            logger.warning(
                f"Skipping {model_api} / {variation_key}: no cost/token data"
            )
            continue

        cost, input_tokens, output_tokens = result

        buckets.append(
            BucketData(
                model=model_api,
                variation=variation_key,
                current_samples=tot,
                misaligned_count=mis,
                cost_per_sample=cost,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )

    return buckets


def filter_buckets(
    buckets: list[BucketData], min_total_samples: int
) -> list[BucketData]:
    """Filter to models with at least min_total_samples across all variations."""
    # Sum samples per model
    model_totals: dict[str, int] = defaultdict(int)
    for b in buckets:
        model_totals[b.model] += b.current_samples

    # Filter
    valid_models = {m for m, t in model_totals.items() if t >= min_total_samples}
    logger.info(f"Models with >= {min_total_samples} samples: {len(valid_models)}")

    return [b for b in buckets if b.model in valid_models]


def compute_posterior_estimate(
    k: int, n: int, prior_alpha: float = 1.0, prior_beta: float = 9.0
) -> float:
    """Compute posterior mean for misalignment rate using Beta prior.

    Args:
        k: Number of misaligned samples observed
        n: Total samples observed
        prior_alpha: Beta prior alpha parameter (default 1)
        prior_beta: Beta prior beta parameter (default 9, giving 10% prior mean)

    Returns:
        Posterior mean estimate of misalignment rate
    """
    return (k + prior_alpha) / (n + prior_alpha + prior_beta)


def optimize_allocation(
    buckets: list[BucketData],
    budget: float,
    value_fn: Callable[[float, float], float] | None = None,
    max_samples_per_bucket: int | None = None,
    min_budget_per_bucket: float = 10.0,
) -> dict[tuple[str, str], int]:
    """
    Optimize sample allocation to maximize total value.

    Args:
        buckets: List of bucket data
        budget: Total budget in USD
        value_fn: Function(n, p) -> value. Default is odds_ratio_value which
                  computes value based on precision of log-odds estimation.
                  p is posterior misalignment probability estimate.
        max_samples_per_bucket: Maximum samples allowed per bucket (None = unlimited)
        min_budget_per_bucket: Minimum budget allocation per bucket in USD (default $10)

    Returns:
        Dict of (model, variation) -> optimal total sample count
    """
    if value_fn is None:
        value_fn = odds_ratio_value

    # All buckets are now active - we use posterior estimates instead of filtering
    active_buckets = buckets

    logger.info(f"Total buckets for optimization: {len(active_buckets)}")

    if not active_buckets:
        logger.warning("No buckets to optimize!")
        return {}

    # Current state
    current_n = np.array([b.current_samples for b in active_buckets], dtype=float)
    costs = np.array([b.cost_per_sample for b in active_buckets])

    # Use posterior estimates instead of raw rates
    posterior_probs = np.array(
        [
            compute_posterior_estimate(b.misaligned_count, b.current_samples)
            for b in active_buckets
        ]
    )

    # Compute minimum additional samples per bucket based on min_budget_per_bucket
    min_additional = np.array(
        [
            max(0, int(np.ceil(min_budget_per_bucket / b.cost_per_sample)))
            for b in active_buckets
        ]
    )

    # Objective: maximize sum of value(n_i, p_i)
    # We minimize negative value
    def objective(additional_n: np.ndarray) -> float:
        total_n = current_n + additional_n
        return -sum(value_fn(n, p) for n, p in zip(total_n, posterior_probs))

    # Constraint: sum(cost_i * additional_n_i) <= budget
    def budget_constraint(additional_n: np.ndarray) -> float:
        return budget - np.dot(costs, additional_n)

    # Bounds: additional_n >= min_additional, and optionally <= (max - current)
    n_buckets = len(active_buckets)
    if max_samples_per_bucket is not None:
        bounds = [
            (
                min_additional[i],
                max(min_additional[i], max_samples_per_bucket - b.current_samples),
            )
            for i, b in enumerate(active_buckets)
        ]
    else:
        bounds = [(min_additional[i], None) for i in range(n_buckets)]

    # Check if minimum allocation exceeds budget
    min_total_cost = np.dot(costs, min_additional)
    if min_total_cost > budget:
        logger.warning(
            f"Minimum allocation (${min_total_cost:,.2f}) exceeds budget (${budget:,.2f})! "
            f"Reducing min_budget_per_bucket proportionally."
        )
        # Scale down minimum allocation to fit budget
        scale = budget * 0.9 / min_total_cost  # Leave 10% for optimization
        min_additional = (min_additional * scale).astype(int)
        bounds = [
            (
                min_additional[i],
                max(min_additional[i], max_samples_per_bucket - b.current_samples)
                if max_samples_per_bucket
                else None,
            )
            for i, b in enumerate(active_buckets)
        ]

    # Initial guess: start from minimum allocation, then distribute remaining budget
    remaining_budget = budget - np.dot(costs, min_additional)
    if remaining_budget > 0:
        inv_cost_sq = 1 / (costs**2)
        initial_weights = inv_cost_sq / inv_cost_sq.sum()
        extra = (remaining_budget / costs) * initial_weights * 0.9  # Safety margin
        initial_additional = min_additional + extra
    else:
        initial_additional = min_additional.astype(float)

    # Optimize
    result = minimize(
        objective,
        initial_additional,
        method="SLSQP",
        bounds=bounds,
        constraints={"type": "ineq", "fun": budget_constraint},
        options={"maxiter": 1000, "ftol": 1e-9},
    )

    if not result.success:
        logger.warning(f"Optimization warning: {result.message}")

    # Build result dict - enforce bounds since SLSQP doesn't strictly respect them
    optimal_additional = np.maximum(result.x, min_additional)  # Ensure at least minimum
    if max_samples_per_bucket is not None:
        max_additional = np.array(
            [max(0, max_samples_per_bucket - b.current_samples) for b in active_buckets]
        )
        optimal_additional = np.minimum(optimal_additional, max_additional)
    optimal_total = current_n + optimal_additional

    allocation = {}
    for b, n in zip(active_buckets, optimal_total):
        allocation[(b.model, b.variation)] = int(round(n))

    return allocation


def write_sample_targets(
    allocation: dict[tuple[str, str], int],
    disabled_models: set[str],
    output_path: Path,
) -> None:
    """Write allocation to sample_targets.json format."""
    # Group by model
    by_model: dict[str, dict[str, int]] = defaultdict(dict)

    for (model, variation), count in allocation.items():
        by_model[model][variation] = count

    # Add disabled models with all zeros
    for model in disabled_models:
        if model not in by_model:
            by_model[model] = {}
        for var in VARIATIONS:
            by_model[model][var] = 0

    # Sort models and variations for consistent output
    targets = {}
    for model in sorted(by_model.keys()):
        targets[model] = {}
        for var in VARIATIONS:  # Use canonical order
            targets[model][var] = by_model[model].get(var, 0)

    output = {"targets": targets}

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    logger.info(f"\nWrote allocation to {output_path}")


def print_results(
    buckets: list[BucketData],
    allocation: dict[tuple[str, str], int],
    total_budget: float,
    existing_cost: float,
    output_format: str = "text",
) -> None:
    """Print the allocation results."""
    # Create lookup for bucket data
    bucket_lookup = {(b.model, b.variation): b for b in buckets}

    # Compute statistics
    total_additional_cost = 0.0
    total_additional_samples = 0
    rows = []

    for (model, variation), optimal_n in sorted(allocation.items()):
        b = bucket_lookup[(model, variation)]
        additional = optimal_n - b.current_samples
        additional_cost = additional * b.cost_per_sample

        total_additional_cost += additional_cost
        total_additional_samples += additional

        # Short model name for display
        short_model = model.split("/")[-1][:25]

        rows.append(
            {
                "model": model,
                "short_model": short_model,
                "variation": variation,
                "current": b.current_samples,
                "optimal": optimal_n,
                "additional": additional,
                "rate": b.misalignment_rate,
                "posterior": b.posterior_rate,
                "cost_per_sample": b.cost_per_sample,
                "additional_cost": additional_cost,
                "input_tokens": b.input_tokens,
                "output_tokens": b.output_tokens,
            }
        )

    if output_format == "csv":
        print(
            "model,variation,current,optimal,additional,rate,cost_per_sample,additional_cost"
        )
        for r in rows:
            print(
                f"{r['model']},{r['variation']},{r['current']},{r['optimal']},"
                f"{r['additional']},{r['rate']:.3f},{r['cost_per_sample']:.4f},"
                f"{r['additional_cost']:.2f}"
            )
    else:
        # Text table
        print("\n" + "=" * 115)
        print("OPTIMAL SAMPLE ALLOCATION")
        print(f"Total budget: ${total_budget:,.0f}")
        print("=" * 115)

        # Header
        print(
            f"{'Model':<26} {'Variation':<20} {'Current':>8} {'Optimal':>8} "
            f"{'Add':>7} {'Raw%':>6} {'Post%':>6} {'$/sample':>9} {'Add$':>10}"
        )
        print("-" * 115)

        for r in rows:
            rate_str = f"{r['rate'] * 100:.1f}" if r["rate"] > 0 else "-"
            post_str = f"{r['posterior'] * 100:.1f}"
            print(
                f"{r['short_model']:<26} {r['variation']:<20} {r['current']:>8} "
                f"{r['optimal']:>8} {r['additional']:>7} {rate_str:>6} {post_str:>6} "
                f"${r['cost_per_sample']:.4f}  ${r['additional_cost']:>9,.2f}"
            )

        print("-" * 100)
        print(
            f"{'TOTAL':<47} {sum(r['current'] for r in rows):>8} "
            f"{sum(r['optimal'] for r in rows):>8} {total_additional_samples:>7} "
            f"{'':>7} {'':>9}  ${total_additional_cost:>9,.2f}"
        )

        print("\n" + "=" * 120)
        print("SUMMARY BY MODEL")
        print("=" * 120)

        # Aggregate by model
        by_model: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "current": 0,
                "optimal": 0,
                "additional": 0,
                "cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
            }
        )
        for r in rows:
            by_model[r["model"]]["current"] += r["current"]
            by_model[r["model"]]["optimal"] += r["optimal"]
            by_model[r["model"]]["additional"] += r["additional"]
            by_model[r["model"]]["cost"] += r["additional_cost"]
            # Tokens used by additional samples
            by_model[r["model"]]["input_tokens"] += r["additional"] * r["input_tokens"]
            by_model[r["model"]]["output_tokens"] += (
                r["additional"] * r["output_tokens"]
            )

        print(
            f"{'Model':<40} {'Current':>8} {'Optimal':>8} {'Add':>8} {'Cost':>11} {'In Tokens':>11} {'Out Tokens':>11}"
        )
        print("-" * 120)
        for model in sorted(by_model.keys()):
            d = by_model[model]
            short = model.split("/")[-1][:38]
            in_tok_str = format_significant(d["input_tokens"])
            out_tok_str = format_significant(d["output_tokens"])
            print(
                f"{short:<40} {d['current']:>8} {d['optimal']:>8} "
                f"{d['additional']:>8} ${d['cost']:>10,.2f} {in_tok_str:>11} {out_tok_str:>11}"
            )

        # Print totals row for model summary
        total_in_tokens = sum(d["input_tokens"] for d in by_model.values())
        total_out_tokens = sum(d["output_tokens"] for d in by_model.values())
        print("-" * 120)
        print(
            f"{'TOTAL':<40} {sum(d['current'] for d in by_model.values()):>8} "
            f"{sum(d['optimal'] for d in by_model.values()):>8} "
            f"{sum(d['additional'] for d in by_model.values()):>8} "
            f"${sum(d['cost'] for d in by_model.values()):>10,.2f} "
            f"{format_significant(total_in_tokens):>11} {format_significant(total_out_tokens):>11}"
        )

        print("\n" + "=" * 100)
        print("SUMMARY BY VARIATION")
        print("=" * 100)

        # Aggregate by variation
        by_var: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"current": 0, "optimal": 0, "additional": 0, "cost": 0.0}
        )
        for r in rows:
            by_var[r["variation"]]["current"] += r["current"]
            by_var[r["variation"]]["optimal"] += r["optimal"]
            by_var[r["variation"]]["additional"] += r["additional"]
            by_var[r["variation"]]["cost"] += r["additional_cost"]

        print(
            f"{'Variation':<45} {'Current':>10} {'Optimal':>10} {'Additional':>10} {'Cost':>12}"
        )
        print("-" * 100)
        for var in sorted(by_var.keys()):
            d = by_var[var]
            print(
                f"{var:<45} {d['current']:>10} {d['optimal']:>10} "
                f"{d['additional']:>10} ${d['cost']:>11,.2f}"
            )

        print("\n" + "=" * 100)
        print(f"Total additional samples: {total_additional_samples:,}")
        print(f"Cost of existing samples: ${existing_cost:,.2f}")
        print(f"Cost of new samples: ${total_additional_cost:,.2f}")
        total_cost = existing_cost + total_additional_cost
        print(f"Total cost: ${total_cost:,.2f}")
        print(f"Budget remaining: ${total_budget - total_cost:,.2f}")
        print("=" * 100)


def main():
    parser = argparse.ArgumentParser(
        description="Compute optimal sample allocation across (model, variation) pairs"
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=25000,
        help="Total budget in USD including existing samples (default: 25000)",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=50,
        help="Minimum total samples for a model to be included (default: 50)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "csv"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=10000,
        help="Maximum samples per bucket (default: 10000, use 0 for unlimited)",
    )
    parser.add_argument(
        "--min-budget",
        type=float,
        default=10.0,
        help="Minimum budget per bucket in USD (default: 10.0)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="configs/final_sample_targets.json",
        help="Output path for sample targets JSON (default: configs/final_sample_targets.json)",
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        help="Don't write output file, only print results",
    )
    args = parser.parse_args()

    # Load data
    listing = load_listing()
    logger.info(f"Loaded {len(listing)} entries from listing.json\n")

    # Load disabled models
    disabled_models = load_disabled_models()
    logger.info("")

    # Collect bucket data
    buckets = collect_bucket_data(listing)
    logger.info(f"Found {len(buckets)} (model, variation) buckets")

    # Filter by minimum samples
    buckets = filter_buckets(buckets, args.min_samples)
    logger.info(f"After filtering by min samples: {len(buckets)} buckets")

    # Filter out disabled models
    buckets = [b for b in buckets if b.model not in disabled_models]
    logger.info(f"After removing disabled models: {len(buckets)} buckets\n")

    # Log value function details
    logger.info("Value function: odds ratio (effect size) precision")
    logger.info("  - 20:1 LR interval: mult_error = exp(4.9 / sqrt(n * p * (1-p)))")
    logger.info(
        "  - 1.2x error -> 90% value, 2x error -> 30% value, 8x error -> 0% value"
    )
    logger.info("  - Assumes ~50/50 split across ablation conditions")
    logger.info("Using Beta(1,9) prior for posterior estimation (10% prior mean)\n")

    # Determine max samples
    max_samples = args.max_samples if args.max_samples > 0 else None
    if max_samples:
        logger.info(f"Max samples per bucket: {max_samples:,}")

    logger.info(f"Min budget per bucket: ${args.min_budget:.2f}\n")

    # Compute cost of existing samples
    existing_cost = sum(b.current_samples * b.cost_per_sample for b in buckets)
    existing_samples = sum(b.current_samples for b in buckets)
    logger.info(f"Existing samples: {existing_samples:,}")
    logger.info(f"Existing cost: ${existing_cost:,.2f}")
    logger.info(f"Total budget: ${args.budget:,.2f}")

    # Budget available for new samples
    budget_for_new = args.budget - existing_cost
    if budget_for_new <= 0:
        logger.warning(
            f"Existing samples already exceed budget! "
            f"(${existing_cost:,.2f} > ${args.budget:,.2f})"
        )
        budget_for_new = 0

    logger.info(f"Budget for new samples: ${budget_for_new:,.2f}\n")

    # Optimize using odds ratio precision value function
    allocation = optimize_allocation(
        buckets, budget_for_new, odds_ratio_value, max_samples, args.min_budget
    )

    # Print results
    print_results(buckets, allocation, args.budget, existing_cost, args.format)

    # Write output file
    if not args.no_output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = Path(__file__).parent.parent / output_path
        write_sample_targets(allocation, disabled_models, output_path)


if __name__ == "__main__":
    main()
