"""Estimate costs for running eval awareness classification.

Uses token estimates from configs/token_estimates.json to calculate actual
transcript lengths per (model, variation) pair.
"""

from typing import Any

from lib.model_registry import get_model_by_api_name
from scripts.transcript_analysis.config import (
    DEFAULT_CLASSIFIER_MODEL,
    S3_EVAL_AWARENESS_LISTING,
    TARGETS_PATH,
    TOKEN_ESTIMATES_PATH,
    load_completed_classifications,
    load_targets,
    load_token_estimates,
)

# Look up classifier pricing from model registry
_classifier_info = get_model_by_api_name(DEFAULT_CLASSIFIER_MODEL)
if _classifier_info is None:
    raise ValueError(
        f"Classifier model '{DEFAULT_CLASSIFIER_MODEL}' not found in model registry"
    )
if _classifier_info.input_cost is None or _classifier_info.output_cost is None:
    raise ValueError(
        f"Classifier model '{DEFAULT_CLASSIFIER_MODEL}' has no pricing in model registry"
    )
CLASSIFIER_INPUT_PRICE_PER_MTK: float = _classifier_info.input_cost
CLASSIFIER_OUTPUT_PRICE_PER_MTK: float = _classifier_info.output_cost

# Classifier overhead (prompt + response)
CLASSIFIER_PROMPT_TOKENS = 500  # Classifier system prompt and instructions
CLASSIFIER_OUTPUT_TOKENS = 300  # Classification verdict + explanation


def _normalize_openrouter_name(model: str) -> str:
    """Normalize openrouter model names for token_estimates lookup.

    Parquet/targets use underscore format (openrouter/google_gemini-2.5-flash)
    but token_estimates uses slash format (openrouter/google/gemini-2.5-flash).
    """
    if model.startswith("openrouter/") and "_" in model.split("/", 1)[1]:
        prefix, rest = model.split("/", 1)
        provider, model_name = rest.split("_", 1)
        return f"{prefix}/{provider}/{model_name}"
    return model


def get_classifier_input_tokens(
    model: str, variation: str, token_estimates: dict[str, dict[str, dict[str, int]]]
) -> int:
    """Get classifier input tokens for a (model, variation) pair.

    Classifier input = transcript (original input + output) + prompt overhead.
    """
    # Normalize openrouter names to match token_estimates format
    normalized = _normalize_openrouter_name(model)
    if normalized not in token_estimates:
        raise KeyError(
            f"Model '{model}' (normalized: '{normalized}') not found in token_estimates.json"
        )
    if variation not in token_estimates[normalized]:
        raise KeyError(
            f"Variation '{variation}' not found for model '{normalized}' in token_estimates.json"
        )

    estimates = token_estimates[normalized][variation]
    transcript_tokens = estimates["input_tokens"] + estimates["output_tokens"]
    return transcript_tokens + CLASSIFIER_PROMPT_TOKENS


def compute_classification_cost(
    model: str,
    variation: str,
    count: int,
    token_estimates: dict[str, dict[str, dict[str, int]]],
) -> float:
    """Compute cost for classifying N transcripts of a (model, variation) pair."""
    input_tokens = (
        get_classifier_input_tokens(model, variation, token_estimates) * count
    )
    output_tokens = CLASSIFIER_OUTPUT_TOKENS * count

    input_cost = input_tokens / 1_000_000 * CLASSIFIER_INPUT_PRICE_PER_MTK
    output_cost = output_tokens / 1_000_000 * CLASSIFIER_OUTPUT_PRICE_PER_MTK

    return input_cost + output_cost


def compute_progress() -> dict[str, Any]:
    """Compute classification progress against targets."""
    targets = load_targets()
    completed = load_completed_classifications()
    token_estimates = load_token_estimates()

    total_target = 0
    total_completed = 0
    total_cost_target = 0.0
    total_cost_completed = 0.0

    by_model: dict[str, dict[str, Any]] = {}
    by_variation: dict[str, dict[str, Any]] = {}

    for model, variations in targets.items():
        model_target = 0
        model_completed = 0
        model_cost_target = 0.0
        model_cost_completed = 0.0

        for variation, target in variations.items():
            if target == 0:
                continue

            done = len(completed.get(model, {}).get(variation, set()))

            cost_per_sample = compute_classification_cost(
                model, variation, 1, token_estimates
            )
            cost_target = cost_per_sample * target
            cost_done = cost_per_sample * done

            model_target += target
            model_completed += done
            model_cost_target += cost_target
            model_cost_completed += cost_done

            if variation not in by_variation:
                by_variation[variation] = {
                    "target": 0,
                    "completed": 0,
                    "cost_target": 0.0,
                    "cost_completed": 0.0,
                }
            by_variation[variation]["target"] += target
            by_variation[variation]["completed"] += done
            by_variation[variation]["cost_target"] += cost_target
            by_variation[variation]["cost_completed"] += cost_done

        if model_target > 0:
            by_model[model] = {
                "target": model_target,
                "completed": model_completed,
                "remaining": max(0, model_target - model_completed),
                "cost_target": model_cost_target,
                "cost_completed": model_cost_completed,
                "cost_remaining": model_cost_target - model_cost_completed,
            }

        total_target += model_target
        total_completed += model_completed
        total_cost_target += model_cost_target
        total_cost_completed += model_cost_completed

    return {
        "total_target": total_target,
        "total_completed": total_completed,
        "total_remaining": max(0, total_target - total_completed),
        "total_cost_target": total_cost_target,
        "total_cost_completed": total_cost_completed,
        "total_cost_remaining": total_cost_target - total_cost_completed,
        "by_model": by_model,
        "by_variation": by_variation,
    }


def print_estimate() -> None:
    """Print a formatted cost estimate with progress."""
    progress = compute_progress()

    total_target = progress["total_target"]
    total_completed = progress["total_completed"]
    total_remaining = progress["total_remaining"]
    cost_completed = progress["total_cost_completed"]
    cost_remaining = progress["total_cost_remaining"]
    cost_total = progress["total_cost_target"]

    print("=" * 70)
    print("EVAL AWARENESS CLASSIFICATION COST ESTIMATE")
    print("=" * 70)
    print()
    print(f"Targets from: {TARGETS_PATH.name}")
    print(f"Token estimates from: {TOKEN_ESTIMATES_PATH.name}")
    print(f"Results from: {S3_EVAL_AWARENESS_LISTING}")
    print()
    print(f"  Target:     {total_target:,} transcripts")
    print(f"  Completed:  {total_completed:,} transcripts")
    print(f"  Remaining:  {total_remaining:,} transcripts")
    if total_target > 0:
        pct = 100 * total_completed / total_target
        print(f"  Progress:   {pct:.1f}%")
    print()
    print(
        f"  Pricing: ${CLASSIFIER_INPUT_PRICE_PER_MTK:.2f}/MTok input, "
        f"${CLASSIFIER_OUTPUT_PRICE_PER_MTK:.2f}/MTok output"
    )
    print()
    print(f"  Cost so far:    ${cost_completed:,.2f}")
    print(f"  Cost remaining: ${cost_remaining:,.2f}")
    print(f"  Total target:   ${cost_total:,.2f}")
    print()
    print(f"{'Model':<42} {'Done':>5} {'Tgt':>5} {'Rem':>5} {'Cost':>10}")
    print("-" * 70)
    for model, stats in sorted(progress["by_model"].items()):
        short_model = model.split("/")[-1][:40]
        print(
            f"{short_model:<42} {stats['completed']:>5} {stats['target']:>5} "
            f"{stats['remaining']:>5} ${stats['cost_remaining']:>8,.2f}"
        )
    print()
    print(f"{'Variation':<45} {'Done':>5} {'Tgt':>5} {'Cost':>12}")
    print("-" * 70)
    for variation, stats in sorted(progress["by_variation"].items()):
        cost_rem = stats["cost_target"] - stats["cost_completed"]
        print(
            f"{variation:<45} {stats['completed']:>5} {stats['target']:>5} "
            f"${cost_rem:>10,.2f}"
        )
    print()


if __name__ == "__main__":
    print_estimate()
