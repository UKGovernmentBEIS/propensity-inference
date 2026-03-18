#!/usr/bin/env python3
"""Run entropy estimation on selected (model, variation) pairs.

These 8 pairs cover all 4 providers (2 each) with npq >= 100 for reliable estimation.

Usage:
    uv run scripts/entropy/run_targets.py run
    uv run scripts/entropy/run_targets.py run --workers 8
    uv run scripts/entropy/run_targets.py run --dry-run
    uv run scripts/entropy/run_targets.py list
"""

import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any

import fire

# 8 (model, scenario, variation) targets for entropy estimation
# Selected to cover all 4 providers with npq = n * p * (1-p) >= 100
ENTROPY_TARGETS = [
    ("anthropic/claude-3-5-haiku-20241022", "agentic_misalignment_v2", "alert"),
    (
        "anthropic/claude-sonnet-4-5-20250929",
        "gpu_decision_email_assistant",
        "gpu_decision",
    ),
    (
        "openrouter/google/gemini-2.5-flash",
        "agentic_misalignment_v2",
        "leak-starsentinel",
    ),
    ("openrouter/google/gemini-2.5-pro", "agentic_misalignment_v2", "leak-doj"),
    ("openrouter/meta-llama/llama-3.3-70b-instruct", "sem_v2", "summarization"),
    ("openrouter/meta-llama/llama-4-scout", "sem_v2", "classification"),
    (
        "openrouter/openai/gpt-oss-120b",
        "hiding_reward_hacking",
        "hiding_reward_hacking",
    ),
    ("openai/o4-mini-2025-04-16", "email_spam_filter_v2", "email_spam_filter"),
]


def list_targets():
    """List all entropy targets."""
    print(f"{'Idx':<4} {'Model':<50} {'Variation':<25}")
    print("-" * 80)
    for i, (model, scenario, variation) in enumerate(ENTROPY_TARGETS):
        print(f"{i:<4} {model:<50} {variation:<25}")


def _run_single(
    model: str,
    scenario: str,
    variation: str,
    idx: int,
    num_samples: int,
    upload: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Run entropy estimation for a single target."""
    cmd = [
        "uv",
        "run",
        "scripts/entropy/estimate.py",
        "run-samples",
        model,
        scenario,
        variation,
        "--num-samples",
        str(num_samples),
    ]
    if dry_run:
        cmd.append("--dry-run")
    if not upload:
        cmd.extend(["--upload-to-s3", "False"])

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return {"idx": idx, "model": model, "variation": variation, "success": True}
    except subprocess.CalledProcessError as e:
        return {
            "idx": idx,
            "model": model,
            "variation": variation,
            "success": False,
            "error": e.stderr,
        }


def run(
    target_idx: int | None = None,
    dry_run: bool = False,
    num_samples: int = 500,
    upload: bool = True,
    workers: int = 4,
):
    """Run entropy estimation on targets.

    Args:
        target_idx: Run only this target (0-7). Otherwise run all.
        dry_run: Don't actually run sampling.
        num_samples: Number of config samples per target.
        upload: Upload results to S3.
        workers: Parallel workers.
    """
    if target_idx is not None:
        if not 0 <= target_idx < len(ENTROPY_TARGETS):
            print(f"Error: target_idx must be 0-{len(ENTROPY_TARGETS) - 1}")
            sys.exit(1)
        model, scenario, variation = ENTROPY_TARGETS[target_idx]
        print(f"Running: {model} / {variation}")
        result = _run_single(
            model, scenario, variation, target_idx, num_samples, upload, dry_run
        )
        print(
            "SUCCESS"
            if result["success"]
            else f"FAILED: {result.get('error', '')[:500]}"
        )
        return

    print(f"Running {len(ENTROPY_TARGETS)} targets with {workers} workers\n")
    results: list[dict[str, Any]] = []

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_run_single, m, s, v, i, num_samples, upload, dry_run): i
            for i, (m, s, v) in enumerate(ENTROPY_TARGETS)
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = "SUCCESS" if result["success"] else "FAILED"
            print(
                f"[{len(results)}/{len(ENTROPY_TARGETS)}] {status}: {result['model']} / {result['variation']}"
            )

    n_success = sum(1 for r in results if r["success"])
    print(f"\nDone: {n_success}/{len(results)} succeeded")


if __name__ == "__main__":
    fire.Fire({"run": run, "list": list_targets})
