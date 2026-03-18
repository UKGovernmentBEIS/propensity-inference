#!/usr/bin/env python3
"""Eval awareness GLM fitting for Claude 4.5 models.

Fits per-model Bayesian GLMs predicting P(eval awareness) from the 12 scenario
parameters, one fit per Claude 4.5 model. Uses model_variation intercepts +
global parameter coefficients. Outcome: eval_aware (YES/UNSURE -> 1, NO -> 0).

Output: paper_cache/posteriors/pooled/per-model_eval_awareness/{model_slug}.npz

Usage:
    # Fit all 3 models
    uv run scripts/paper/run_eval_awareness_fits.py fit

    # Quick test
    uv run scripts/paper/run_eval_awareness_fits.py fit --ultra

    # Fast mode
    uv run scripts/paper/run_eval_awareness_fits.py fit --fast

    # Control parallelism
    uv run scripts/paper/run_eval_awareness_fits.py fit --workers 4
"""

import json
import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fire
import numpy as np

from lib.pooled_fitting import fit_pooled_regression, load_all_samples

logger = logging.getLogger(__name__)

_S3_ROOT = os.environ.get("PROPENSITY_S3_ROOT", "propensity")
_S3_MOUNT = os.environ.get("S3_MOUNT_POINT", "")
EVAL_AWARENESS_LISTING = Path(
    f"{_S3_MOUNT}/{_S3_ROOT}/evals/logs/eval_awareness_listing.json"
)

CLAUDE_45_MODELS = [
    "anthropic/claude-opus-4-5-20251101",
    "anthropic/claude-sonnet-4-5-20250929",
    "anthropic/claude-haiku-4-5-20251001",
]

OUTPUT_DIR = Path("paper_cache/posteriors/pooled/per-model_eval_awareness")


def setup_logging() -> Path:
    """Set up logging to both console and file."""
    logs_dir = Path("paper_cache/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"eval_awareness_fits_{timestamp}.log"

    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_format)

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(file_handler)

    return log_file


_log_file: Path | None = None


def model_id_to_slug(model_id: str) -> str:
    """Convert model ID to filesystem-safe slug."""
    return model_id.replace("/", "_").replace(":", "_")


def load_eval_awareness_labels() -> dict[str, int]:
    """Load eval awareness labels and map to binary.

    Returns:
        Dict mapping eval_path -> binary label (1 for YES/UNSURE, 0 for NO).
        ERROR entries are excluded.
    """
    if not EVAL_AWARENESS_LISTING.exists():
        raise FileNotFoundError(
            f"Eval awareness listing not found: {EVAL_AWARENESS_LISTING}"
        )

    with open(EVAL_AWARENESS_LISTING) as f:
        data = json.load(f)

    entries = data["entries"]
    labels: dict[str, int] = {}

    for eval_path, entry in entries.items():
        awareness = entry["eval_awareness"]
        if awareness in ("YES", "UNSURE"):
            labels[eval_path] = 1
        elif awareness == "NO":
            labels[eval_path] = 0
        # Skip ERROR entries

    return labels


def load_samples_with_eval_awareness():
    """Load all samples and join with eval awareness labels.

    Returns:
        DataFrame with new 'eval_aware' column (1/0/NaN).
        NaN for samples without eval awareness labels.
    """
    df = load_all_samples()
    labels = load_eval_awareness_labels()

    # Map meta_eval_file to binary eval_aware
    df["eval_aware"] = df["meta_eval_file"].map(labels)

    n_labeled = df["eval_aware"].notna().sum()
    n_total = len(df)
    n_aware = (df["eval_aware"] == 1).sum()
    n_not_aware = (df["eval_aware"] == 0).sum()

    logger.info(
        f"Eval awareness labels: {n_labeled}/{n_total} samples labeled "
        f"({n_aware} aware, {n_not_aware} not aware)"
    )

    return df


@dataclass
class AwarenessFitWorkItem:
    """Work item for eval awareness fitting."""

    model: str
    mcmc_mode: str | None
    mcmc_override: dict[str, int] | None = None

    @property
    def item_id(self) -> str:
        return model_id_to_slug(self.model)


def fit_awareness_worker(work_item: AwarenessFitWorkItem) -> dict[str, Any]:
    """Fit a single per-model eval awareness GLM (worker function).

    Each worker loads data independently to avoid shared state issues.
    """
    try:
        df = load_samples_with_eval_awareness()

        # Filter to single model
        df = df[df["meta_model"] == work_item.model]

        # Drop rows without eval awareness labels
        df = df[df["eval_aware"].notna()]

        if len(df) == 0:
            return {
                "item_id": work_item.item_id,
                "status": "skipped",
                "reason": "no_data_after_filter",
            }

        n_models = df["meta_model"].nunique()
        n_variations = df["variation"].nunique()
        n_samples = len(df)

        logger.info(
            f"Fitting {work_item.item_id}: {n_samples} samples, "
            f"{n_models} models, {n_variations} variations"
        )

        # Swap meta_score with eval_aware (predict awareness)
        df["meta_score"] = df["eval_aware"].astype(int)
        result = fit_pooled_regression(
            df=df,
            mcmc_mode=work_item.mcmc_mode,
            mcmc_override=work_item.mcmc_override,
        )

        # Save posteriors
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        posterior_path = OUTPUT_DIR / f"{work_item.item_id}.npz"
        np.savez(posterior_path, **result.posteriors)
        logger.info(f"Saved posteriors to {posterior_path}")

        # Build and save summary
        summary = {
            "item_id": work_item.item_id,
            "model": work_item.model,
            "n_samples": n_samples,
            "n_models": n_models,
            "n_variations": n_variations,
            "models": sorted(df["meta_model"].unique().tolist()),
            "variations": sorted(df["variation"].unique().tolist()),
            "eval_awareness_rate": float(df["meta_score"].mean()),
            **result.summary,
            "convergence_ok": result.convergence_ok,
            "convergence_issues": result.convergence_issues,
            "fit_timestamp": datetime.now(UTC).isoformat(),
            "mcmc_mode": work_item.mcmc_mode,
        }

        summary_path = OUTPUT_DIR / f"{work_item.item_id}.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        return {
            "item_id": work_item.item_id,
            "status": "done",
            "n_samples": n_samples,
            "S_mean": result.summary.get("S_mean", 0),
        }

    except Exception as e:
        logger.error(f"Error fitting {work_item.item_id}: {e}")
        import traceback

        traceback.print_exc()
        return {
            "item_id": work_item.item_id,
            "status": "error",
            "error": str(e),
        }


class EvalAwarenessFitter:
    """CLI for eval awareness GLM fitting."""

    def fit(
        self,
        fast: bool = False,
        ultra: bool = False,
        workers: int = 3,
    ):
        """Fit per-model eval awareness GLMs for Claude 4.5 models.

        Args:
            fast: Use fast MCMC (500 samples, 2 chains)
            ultra: Use ultra-fast MCMC (100 samples, 2 chains)
            workers: Number of parallel workers
        """
        import time

        if ultra:
            mcmc_mode = "ultra"
        elif fast:
            mcmc_mode = "fast"
        else:
            mcmc_mode = None

        work_items = [
            AwarenessFitWorkItem(model=model, mcmc_mode=mcmc_mode)
            for model in CLAUDE_45_MODELS
        ]

        print("\n=== Eval Awareness Fitting (Type A: per-model) ===")
        print(f"Log file: {_log_file}")
        print(f"Models: {len(work_items)}")
        print(f"MCMC mode: {mcmc_mode or 'full'}")
        print(f"Workers: {workers}")
        print()

        results = []
        completed = 0
        start_time = time.time()

        try:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(fit_awareness_worker, item): item
                    for item in work_items
                }

                for future in as_completed(futures):
                    item = futures[future]
                    completed += 1

                    try:
                        result = future.result()
                        results.append(result)

                        elapsed = time.time() - start_time
                        status = result.get("status", "unknown")
                        item_id = result["item_id"]

                        if status == "skipped":
                            print(
                                f"[{completed}/{len(work_items)}] {item_id}: "
                                f"SKIPPED ({result.get('reason', '')})"
                            )
                        elif status == "error":
                            print(
                                f"[{completed}/{len(work_items)}] {item_id}: "
                                f"ERROR - {result.get('error', '')[:80]}"
                            )
                        else:
                            s = result.get("S_mean", 0)
                            print(
                                f"[{completed}/{len(work_items)}] {item_id}: "
                                f"DONE (S={s:.3f}, {elapsed:.0f}s)"
                            )

                    except Exception as e:
                        print(
                            f"[{completed}/{len(work_items)}] {item.item_id}: "
                            f"EXCEPTION - {e}"
                        )
                        results.append(
                            {
                                "item_id": item.item_id,
                                "status": "error",
                                "error": str(e),
                            }
                        )

        except KeyboardInterrupt:
            print("\n\nInterrupted! Progress has been saved.")

        # Print summary
        print("\n=== Fitting Complete ===\n")
        n_done = sum(1 for r in results if r.get("status") == "done")
        n_error = sum(1 for r in results if r.get("status") == "error")
        n_skipped = sum(1 for r in results if r.get("status") == "skipped")
        print(f"Done: {n_done}, Errors: {n_error}, Skipped: {n_skipped}")


def main():
    global _log_file
    _log_file = setup_logging()
    fire.Fire(EvalAwarenessFitter)


if __name__ == "__main__":
    main()
