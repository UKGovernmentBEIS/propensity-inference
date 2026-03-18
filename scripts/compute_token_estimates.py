#!/usr/bin/env python3
"""Compute actual token usage per (model, variation) pair from S3 eval files.

Samples N evals per pair and computes average input/output tokens.

Usage:
    uv run python scripts/compute_token_estimates.py
    uv run python scripts/compute_token_estimates.py --samples 20
    uv run python scripts/compute_token_estimates.py --output configs/token_estimates.json
"""

import argparse
import json
import logging
import os
import random
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from inspect_ai.log import read_eval_log

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Variations we care about (scenario/variation format)
VARIATIONS = [
    "agentic_misalignment_v2/alert",
    "agentic_misalignment_v2/leak-starsentinel",
    "agentic_misalignment_v2/leak-doj",
    "email_spam_filter_v2/email_spam_filter",
    "gpu_decision_email_assistant/gpu_decision",
    "hiding_reward_hacking/hiding_reward_hacking",
    "power_preservation/threat",
    "power_preservation/enhancement",
    "power_preservation/expansion",
    "sem_v2/classification",
    "sem_v2/summarization",
]


@dataclass
class TokenUsage:
    """Token usage with all sources aggregated for cost estimation.

    input_tokens: input + cache_write + 0.1*cache_read (weighted by cost)
    output_tokens: output + reasoning
    """

    input_tokens: int
    output_tokens: int


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


def group_evals_by_model_variation(
    listing: dict[str, Any],
) -> dict[tuple[str, str], list[str]]:
    """Group eval paths by (model, variation) pair."""
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)

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

        model = entry.get("model", "unknown")
        # Convert S3 name to API name
        if "_" in model:
            parts_model = model.split("_", 1)
            model = f"{parts_model[0]}/{parts_model[1]}"

        groups[(model, variation_key)].append(path)

    return groups


def get_token_usage_from_eval(bucket: str, eval_path: str) -> TokenUsage | None:
    """Download eval and extract token usage for the subject model.

    Aggregates tokens as:
    - input_tokens = input_tokens + cache_write + cache_read (all input sources)
    - output_tokens = output_tokens + reasoning_tokens (all output sources)
    """
    s3 = boto3.client("s3")
    s3_root = os.environ.get("PROPENSITY_S3_ROOT", "propensity")
    full_key = f"{s3_root}/evals/logs/{eval_path}"
    temp_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(suffix=".eval", delete=False) as f:
            temp_path = f.name

        s3.download_file(bucket, full_key, temp_path)
        log = read_eval_log(temp_path)

        # Get model usage - the subject model should be in the path
        # Extract model from path: scenario/variation/version/model/filename.eval
        parts = eval_path.split("/")
        if len(parts) >= 4:
            model_s3 = parts[3]

            if log.stats and log.stats.model_usage:
                # Find the matching model in model_usage by converting API names to S3 format
                # e.g., "openrouter/google/gemini-2.5-flash" -> "openrouter_google_gemini-2.5-flash"
                usage = None
                for model_api, model_usage in log.stats.model_usage.items():
                    if model_api.replace("/", "_") == model_s3:
                        usage = model_usage
                        break
                if usage:
                    # Sum all input sources (cache_read at 0.1x since it's cheaper)
                    total_input = (
                        (usage.input_tokens or 0)
                        + (usage.input_tokens_cache_write or 0)
                        + 0.1 * (usage.input_tokens_cache_read or 0)
                    )
                    # Sum all output sources (including reasoning)
                    total_output = (usage.output_tokens or 0) + (
                        usage.reasoning_tokens or 0
                    )

                    return TokenUsage(
                        input_tokens=int(total_input),
                        output_tokens=int(total_output),
                    )

        return None
    except Exception as e:
        logger.warning(f"Error reading {eval_path}: {e}")
        return None
    finally:
        if temp_path is not None:
            Path(temp_path).unlink(missing_ok=True)


def compute_token_estimates(
    listing: dict[str, Any], samples_per_pair: int = 10
) -> dict[tuple[str, str], TokenUsage]:
    """Compute average token usage per (model, variation) pair."""
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        raise ValueError("S3_BUCKET not set")

    groups = group_evals_by_model_variation(listing)
    logger.info(f"Found {len(groups)} (model, variation) pairs")

    estimates: dict[tuple[str, str], TokenUsage] = {}
    total_pairs = len(groups)

    for i, ((model, variation), paths) in enumerate(sorted(groups.items())):
        # Sample up to N evals
        sample_paths = random.sample(paths, min(samples_per_pair, len(paths)))

        input_tokens = []
        output_tokens = []

        for path in sample_paths:
            usage = get_token_usage_from_eval(bucket, path)
            if usage:
                input_tokens.append(usage.input_tokens)
                output_tokens.append(usage.output_tokens)

        if input_tokens:
            estimates[(model, variation)] = TokenUsage(
                input_tokens=int(sum(input_tokens) / len(input_tokens)),
                output_tokens=int(sum(output_tokens) / len(output_tokens)),
            )

            logger.info(
                f"[{i + 1}/{total_pairs}] {model[:30]:30} {variation:40} "
                f"in={estimates[(model, variation)].input_tokens:>7,} "
                f"out={estimates[(model, variation)].output_tokens:>6,} "
                f"(n={len(input_tokens)})"
            )
        else:
            logger.warning(
                f"[{i + 1}/{total_pairs}] {model[:30]:30} {variation:40} NO DATA"
            )

    return estimates


def format_significant(n: int, sig_figs: int = 2) -> int:
    """Round to N significant figures."""
    if n == 0:
        return 0
    from math import floor, log10

    magnitude = floor(log10(abs(n)))
    factor = 10 ** (magnitude - sig_figs + 1)
    return int(round(n / factor) * factor)


def compute_variation_averages(
    estimates: dict[tuple[str, str], TokenUsage],
) -> dict[str, TokenUsage]:
    """Compute average token usage per variation across all models."""
    by_variation: dict[str, list[TokenUsage]] = defaultdict(list)
    for (_, variation), usage in estimates.items():
        by_variation[variation].append(usage)

    averages = {}
    for variation, usages in by_variation.items():
        if usages:
            averages[variation] = TokenUsage(
                input_tokens=sum(u.input_tokens for u in usages) // len(usages),
                output_tokens=sum(u.output_tokens for u in usages) // len(usages),
            )
    return averages


def write_estimates(
    estimates: dict[tuple[str, str], TokenUsage],
    output_path: Path,
    all_models: set[str] | None = None,
) -> None:
    """Write estimates to JSON file.

    For missing (model, variation) pairs, uses variation average as fallback.
    """
    # Compute variation averages for fallback
    variation_averages = compute_variation_averages(estimates)

    # Get all models (from estimates + provided set)
    models_in_estimates = set(m for m, _ in estimates.keys())
    all_models = all_models or models_in_estimates

    # Convert to serializable format, filling in missing pairs
    data: dict[str, dict[str, Any]] = {"token_estimates": {}}

    for model in sorted(all_models):
        data["token_estimates"][model] = {}
        for variation in VARIATIONS:
            if (model, variation) in estimates:
                usage = estimates[(model, variation)]
                data["token_estimates"][model][variation] = {
                    "input_tokens": format_significant(usage.input_tokens),
                    "output_tokens": format_significant(usage.output_tokens),
                }
            elif variation in variation_averages:
                # Use variation average as fallback
                avg = variation_averages[variation]
                data["token_estimates"][model][variation] = {
                    "input_tokens": format_significant(avg.input_tokens),
                    "output_tokens": format_significant(avg.output_tokens),
                    "estimated": True,  # Flag that this is an estimate
                }
                logger.info(
                    f"Using variation average for {model} / {variation}: "
                    f"in={avg.input_tokens}, out={avg.output_tokens}"
                )

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"\nWrote estimates to {output_path}")


def print_summary(estimates: dict[tuple[str, str], TokenUsage]) -> None:
    """Print summary statistics."""
    print("\n" + "=" * 80)
    print("TOKEN USAGE SUMMARY (rounded to 2 significant figures)")
    print("=" * 80)

    # Group by model
    by_model: dict[str, list[TokenUsage]] = defaultdict(list)
    for (model, _), usage in estimates.items():
        by_model[model].append(usage)

    print(f"\n{'Model':<45} {'Avg Input':>12} {'Avg Output':>12}")
    print("-" * 70)

    for model in sorted(by_model.keys()):
        usages = by_model[model]
        avg_in = format_significant(sum(u.input_tokens for u in usages) // len(usages))
        avg_out = format_significant(
            sum(u.output_tokens for u in usages) // len(usages)
        )

        short_model = model.split("/")[-1][:43]
        print(f"{short_model:<45} {avg_in:>12,} {avg_out:>12,}")

    # Group by variation
    print("\n")
    print(f"{'Variation':<45} {'Avg Input':>12} {'Avg Output':>12}")
    print("-" * 70)

    by_variation: dict[str, list[TokenUsage]] = defaultdict(list)
    for (_, variation), usage in estimates.items():
        by_variation[variation].append(usage)

    for variation in sorted(by_variation.keys()):
        usages = by_variation[variation]
        avg_in = format_significant(sum(u.input_tokens for u in usages) // len(usages))
        avg_out = format_significant(
            sum(u.output_tokens for u in usages) // len(usages)
        )

        print(f"{variation:<45} {avg_in:>12,} {avg_out:>12,}")


def main():
    parser = argparse.ArgumentParser(
        description="Compute token usage estimates from S3 eval files"
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=10,
        help="Number of samples per (model, variation) pair (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="configs/token_estimates.json",
        help="Output path for estimates JSON (default: configs/token_estimates.json)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    args = parser.parse_args()

    random.seed(args.seed)

    listing = load_listing()
    logger.info(f"Loaded {len(listing)} entries\n")

    # Get all models from the listing
    groups = group_evals_by_model_variation(listing)
    all_models = set(model for model, _ in groups.keys())

    estimates = compute_token_estimates(listing, args.samples)

    print_summary(estimates)

    # Write output (will fill in missing pairs with variation averages)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path(__file__).parent.parent / output_path
    write_estimates(estimates, output_path, all_models)


if __name__ == "__main__":
    main()
