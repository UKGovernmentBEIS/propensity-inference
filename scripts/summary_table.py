#!/usr/bin/env python3
"""Generate summary table of misalignment rates by model and variation.

Queries the listing.json from S3 (fast) and produces a table with:
- Rows: models
- Columns: variations
- Cells: "20% (1/5)" format showing misalignment rate and sample counts

Usage:
    uv run python scripts/summary_table.py
    uv run python scripts/summary_table.py --format csv
    uv run python scripts/summary_table.py --format markdown
"""

import argparse
import json
import logging
import os
from collections import defaultdict
from typing import Any, Literal

import boto3

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# All scenario/variation pairs
VARIATIONS = [
    ("agentic_misalignment_v2", "alert"),
    ("agentic_misalignment_v2", "leak-starsentinel"),
    ("agentic_misalignment_v2", "leak-doj"),
    ("email_spam_filter_v2", "email_spam_filter"),
    ("gpu_decision_email_assistant", "gpu_decision"),
    ("hiding_reward_hacking", "hiding_reward_hacking"),
    ("power_preservation", "threat"),
    ("power_preservation", "enhancement"),
    ("power_preservation", "expansion"),
    ("sem_v2", "classification"),
    ("sem_v2", "summarization"),
]

# Short column names for display
SHORT_NAMES = {
    "agentic_misalignment_v2/alert": "am/alert",
    "agentic_misalignment_v2/leak-starsentinel": "am/leak-ss",
    "agentic_misalignment_v2/leak-doj": "am/leak-doj",
    "email_spam_filter_v2/email_spam_filter": "spam",
    "gpu_decision_email_assistant/gpu_decision": "gpu",
    "hiding_reward_hacking/hiding_reward_hacking": "hide-rh",
    "power_preservation/threat": "pp/threat",
    "power_preservation/enhancement": "pp/enhance",
    "power_preservation/expansion": "pp/expand",
    "sem_v2/classification": "sem/class",
    "sem_v2/summarization": "sem/summ",
}


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


def collect_results(listing: dict[str, Any]) -> dict[str, dict[str, tuple[int, int]]]:
    """Collect results from listing.json.

    Returns:
        Dict of model -> variation_key -> (misaligned_count, total_count)
    """
    # Structure: model -> variation_key -> (misaligned, total)
    results: dict[str, dict[str, tuple[int, int]]] = defaultdict(
        lambda: defaultdict(lambda: (0, 0))
    )

    for path, entry in listing.items():
        # Parse path: scenario/variation/version/model/filename.eval
        parts = path.split("/")
        if len(parts) < 4:
            continue

        scenario = parts[0]
        variation = parts[1]
        # Skip entropy subdirectory files
        if "entropy" in path:
            continue

        variation_key = f"{scenario}/{variation}"

        # Check if this variation is in our list
        if (scenario, variation) not in VARIATIONS:
            continue

        # Only count successful evals
        if entry.get("status") != "success":
            continue

        model = entry.get("model", "unknown")

        # Get score from primary_metric
        primary_metric = entry.get("primary_metric", {})
        score = primary_metric.get("value")

        if score is not None:
            misaligned, total = results[model][variation_key]
            results[model][variation_key] = (misaligned + int(score), total + 1)

    return dict(results)


def format_cell(misaligned: int, total: int) -> str:
    """Format a cell as 'XX% (n/N)'."""
    if total == 0:
        return "-"
    pct = (misaligned / total) * 100
    return f"{pct:.0f}% ({misaligned}/{total})"


def print_table(
    results: dict[str, dict[str, tuple[int, int]]],
    output_format: Literal["text", "csv", "markdown"] = "text",
) -> None:
    """Print the summary table."""
    if not results:
        print("No results found.")
        return

    # Get all models and variations
    models = sorted(results.keys())
    variation_keys = [f"{s}/{v}" for s, v in VARIATIONS]

    if output_format == "csv":
        # CSV output
        headers = (
            ["model"] + [SHORT_NAMES.get(v, v) for v in variation_keys] + ["TOTAL"]
        )
        print(",".join(headers))

        for model in models:
            row = [model]
            row_mis, row_tot = 0, 0
            for var_key in variation_keys:
                mis, tot = results[model].get(var_key, (0, 0))
                row.append(format_cell(mis, tot))
                row_mis += mis
                row_tot += tot
            row.append(format_cell(row_mis, row_tot))
            print(",".join(row))

    elif output_format == "markdown":
        # Markdown table
        headers = (
            ["Model"] + [SHORT_NAMES.get(v, v) for v in variation_keys] + ["TOTAL"]
        )
        print("| " + " | ".join(headers) + " |")
        print("| " + " | ".join(["---"] * len(headers)) + " |")

        for model in models:
            short_model = model.split("/")[-1][:30]
            row = [short_model]
            row_mis, row_tot = 0, 0
            for var_key in variation_keys:
                mis, tot = results[model].get(var_key, (0, 0))
                row.append(format_cell(mis, tot))
                row_mis += mis
                row_tot += tot
            row.append(format_cell(row_mis, row_tot))
            print("| " + " | ".join(row) + " |")

    else:
        # Text table with fixed width columns
        col_width = 12
        model_width = 40

        # Header
        header = "Model".ljust(model_width)
        for var_key in variation_keys:
            short = SHORT_NAMES.get(var_key, var_key)[:col_width]
            header += short.center(col_width)
        header += "TOTAL".center(col_width)
        print(header)
        print("=" * len(header))

        # Rows
        for model in models:
            short_model = model.split("/")[-1][: model_width - 1]
            row = short_model.ljust(model_width)
            row_mis, row_tot = 0, 0
            for var_key in variation_keys:
                mis, tot = results[model].get(var_key, (0, 0))
                cell = format_cell(mis, tot)
                row += cell.center(col_width)
                row_mis += mis
                row_tot += tot
            row += format_cell(row_mis, row_tot).center(col_width)
            print(row)

        # Summary row
        print("-" * len(header))
        totals_row = "TOTAL".ljust(model_width)
        grand_mis, grand_tot = 0, 0
        for var_key in variation_keys:
            total_mis = sum(results[m].get(var_key, (0, 0))[0] for m in models)
            total_n = sum(results[m].get(var_key, (0, 0))[1] for m in models)
            cell = format_cell(total_mis, total_n)
            totals_row += cell.center(col_width)
            grand_mis += total_mis
            grand_tot += total_n
        totals_row += format_cell(grand_mis, grand_tot).center(col_width)
        print(totals_row)


def main():
    parser = argparse.ArgumentParser(
        description="Generate misalignment rate summary table"
    )
    parser.add_argument(
        "--format",
        choices=["text", "csv", "markdown"],
        default="text",
        help="Output format (default: text)",
    )
    args = parser.parse_args()

    listing = load_listing()
    logger.info(f"Loaded {len(listing)} entries from listing.json\n")

    results = collect_results(listing)

    print("\n" + "=" * 60)
    print("MISALIGNMENT RATE SUMMARY")
    print("=" * 60 + "\n")

    print_table(results, args.format)


if __name__ == "__main__":
    main()
