#!/usr/bin/env python3
"""Unified CLI for pooled Bayesian regression fitting.

This script handles all pooled fitting modes:
- per-model: Pool across all variations for a single model
- per-variation: Pool across all models for a single variation
- per-quartile: Pool across all variations for models in a capability quartile
- single: Fit a single (model, variation) pair
- all-combined: Pool all 23 models × 11 variations into one giant regression

All modes use:
- Pair-specific intercepts α_{m,v} for each (model, variation) pair
- √n weighting for variations within scenarios
- Zero-out for unimplemented parameters
- All 12 parameters (some may be uninformative if all-zero)

Usage:
    # Per-model pooled (one model × all variations)
    uv run scripts/paper/run_pooled_fits.py fit --model "anthropic/claude-3-5-haiku-20241022"

    # Per-variation pooled (all models × one variation)
    uv run scripts/paper/run_pooled_fits.py fit --variation "alert"

    # Per-quartile pooled (quartile × all variations)
    uv run scripts/paper/run_pooled_fits.py fit --quartile q1

    # Single fit (one model × one variation)
    uv run scripts/paper/run_pooled_fits.py fit --model "..." --variation "alert"

    # Giant combined fit (23 models × 11 variations = 253 pair intercepts)
    uv run scripts/paper/run_pooled_fits.py fit --all-combined

    # Batch modes
    uv run scripts/paper/run_pooled_fits.py fit --all-singles        # 253 single fits
    uv run scripts/paper/run_pooled_fits.py fit --all-models         # 23 per-model fits
    uv run scripts/paper/run_pooled_fits.py fit --all-variations     # 11 per-variation fits
    uv run scripts/paper/run_pooled_fits.py fit --all-quartiles      # 4 per-quartile fits

    # Quality modes (tracked, only upgrades)
    uv run scripts/paper/run_pooled_fits.py fit --fast               # 500 samples, 2 chains
    uv run scripts/paper/run_pooled_fits.py fit --ultra              # 100 samples, 2 chains

    # Test mode (custom MCMC, NOT tracked, saves to {mode}_test/)
    uv run scripts/paper/run_pooled_fits.py fit --variation alert --samples 50 --warmup 25 --chains 1

    # Status commands
    uv run scripts/paper/run_pooled_fits.py status --mode per-model
    uv run scripts/paper/run_pooled_fits.py quality --mode per-variation
"""

import json
import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import fire
import numpy as np
import pandas as pd

from lib.analysis.model_capabilities import assign_capability_quartile
from lib.pooled_fitting import (
    fit_pooled_regression,
    load_all_samples,
)
from lib.pooled_fitting.quality import (
    get_quality_summary,
    load_quality_metadata,
    save_quality_metadata,
    should_fit,
    update_quality_metadata,
)


def setup_logging() -> Path:
    """Set up logging to both console and file."""
    logs_dir = Path("paper_cache/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"pooled_fits_{timestamp}.log"

    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_format)

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(file_handler)

    return log_file


# Lazy initialization - set up in main() to avoid side effects at import time
_log_file: Path | None = None
logger = logging.getLogger(__name__)

# Output directories
BASE_OUTPUT_DIR = Path("paper_cache/posteriors/pooled")
QUARTILES = ["q1", "q2", "q3", "q4"]

# Variations excluded for "unambiguous" subset fits
# These scenarios have more ambiguous misalignment signals
UNAMBIGUOUS_EXCLUDED_VARIATIONS = {
    "gpu_decision",
    "hiding_reward_hacking",
    "email_spam_filter",
    "leak-doj",  # AM variation with ambiguous leak target
}


def get_output_dir(mode: str) -> Path:
    """Get output directory for a mode."""
    return BASE_OUTPUT_DIR / mode


def get_quality_file(mode: str) -> Path:
    """Get quality metadata file for a mode."""
    return get_output_dir(mode) / "fit_quality.json"


def model_id_to_slug(model_id: str) -> str:
    """Convert model ID to filesystem-safe slug."""
    return model_id.replace("/", "_").replace(":", "_")


@dataclass
class FitWorkItem:
    """Work item for parallel fitting."""

    mode: str  # Base mode (per-model, per-variation, etc.)
    item_id: str  # model slug, variation name, quartile, or "model_variation"
    df_filter: dict[str, Any]  # How to filter the data
    mcmc_mode: str | None
    mcmc_override: dict[str, int] | None = (
        None  # Custom MCMC: {"samples": N, "warmup": N, "chains": N}
    )
    output_mode: str | None = (
        None  # If set, use for output dir (e.g., "per-model_test")
    )
    use_extras: bool = False  # Include scenario-specific extra parameters
    extra_params: dict[str, list[str]] | None = None  # Extra param -> categories
    extra_param_variations: dict[str, list[str]] | None = (
        None  # Extra param -> variations
    )
    use_goal: bool = False  # Include 9-level goal_value_harmonized feature
    exclude_variations: set[str] | None = None  # Variations to exclude from data


def fit_single_item_worker(work_item: FitWorkItem) -> dict[str, Any]:
    """Fit a single item (worker function for multiprocessing).

    This is a module-level function for ProcessPoolExecutor compatibility.
    Each worker loads all data independently to avoid shared state issues.
    """
    from lib.pooled_fitting import load_all_samples

    try:
        # Load all data
        df = load_all_samples()

        # Assign quartiles if needed
        if work_item.mode == "per-quartile":
            all_models = df["meta_model"].unique().tolist()
            df["quartile"] = df["meta_model"].apply(
                lambda m: assign_capability_quartile(m, all_models)
            )

        # Exclude variations if specified (for unambiguous mode)
        if work_item.exclude_variations:
            df = df[~df["variation"].isin(list(work_item.exclude_variations))]

        # Apply filter
        for col, value in work_item.df_filter.items():
            if isinstance(value, list):
                df = cast(pd.DataFrame, df[cast(pd.Series, df[col]).isin(value)])
            else:
                df = cast(pd.DataFrame, df[df[col] == value])

        if len(df) == 0:
            return {
                "item_id": work_item.item_id,
                "mode": work_item.mode,
                "status": "skipped",
                "reason": "no_data_after_filter",
            }

        # Log what we're fitting
        n_models = cast(pd.Series, df["meta_model"]).nunique()
        n_variations = cast(pd.Series, df["variation"]).nunique()
        n_samples = len(df)
        logger.info(
            f"Fitting {work_item.item_id}: {n_samples} samples, "
            f"{n_models} models, {n_variations} variations"
        )

        # Fit
        result = fit_pooled_regression(
            df=df,
            mcmc_mode=work_item.mcmc_mode,
            mcmc_override=work_item.mcmc_override,
            use_extras=work_item.use_extras,
            extra_params=work_item.extra_params,
            extra_param_variations=work_item.extra_param_variations,
            use_goal=work_item.use_goal,
        )

        # Save posteriors (use output_mode if set, otherwise mode)
        save_mode = work_item.output_mode or work_item.mode
        output_dir = get_output_dir(save_mode)
        output_dir.mkdir(parents=True, exist_ok=True)

        posterior_path = output_dir / f"{work_item.item_id}.npz"
        np.savez(posterior_path, allow_pickle=True, **result.posteriors)
        logger.info(f"Saved posteriors to {posterior_path}")

        # Build summary
        summary = {
            "item_id": work_item.item_id,
            "mode": work_item.mode,
            "n_samples": n_samples,
            "n_models": n_models,
            "n_variations": n_variations,
            "models": sorted(cast(pd.Series, df["meta_model"]).unique().tolist()),
            "variations": sorted(cast(pd.Series, df["variation"]).unique().tolist()),
            "misalignment_rate": float(df["meta_score"].mean()),
            **result.summary,
            "convergence_ok": result.convergence_ok,
            "convergence_issues": result.convergence_issues,
            "fit_timestamp": datetime.now(UTC).isoformat(),
            "mcmc_mode": work_item.mcmc_mode,
        }

        summary_path = output_dir / f"{work_item.item_id}.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        return {
            "item_id": work_item.item_id,
            "mode": work_item.mode,
            "status": "done",
            **{
                k: v
                for k, v in summary.items()
                if k in ["S_mean", "p_c_positive", "n_samples"]
            },
        }

    except Exception as e:
        logger.error(f"Error fitting {work_item.item_id}: {e}")
        import traceback

        traceback.print_exc()
        return {
            "item_id": work_item.item_id,
            "mode": work_item.mode,
            "status": "error",
            "error": str(e),
        }


class CLI:
    """Unified CLI for pooled regression fitting."""

    def list(self, mode: str = "all"):
        """List available items for fitting.

        Args:
            mode: "per-model", "per-variation", "per-quartile", or "all"
        """
        print("\n=== Available Items for Fitting ===\n")

        df = load_all_samples()

        if mode in ("per-model", "all"):
            models = sorted(df["meta_model"].unique())
            print(f"Models ({len(models)}):")
            for m in models:
                n = len(df[df["meta_model"] == m])
                print(f"  {m} ({n} samples)")
            print()

        if mode in ("per-variation", "all"):
            variations = sorted(df["variation"].unique())
            print(f"Variations ({len(variations)}):")
            for v in variations:
                n = len(df[df["variation"] == v])
                print(f"  {v} ({n} samples)")
            print()

        if mode in ("per-quartile", "all"):
            all_models = df["meta_model"].unique().tolist()
            df["quartile"] = df["meta_model"].apply(
                lambda m: assign_capability_quartile(m, all_models)
            )
            print("Quartiles:")
            for q in QUARTILES:
                q_df = df[df["quartile"] == q]
                n = len(q_df)
                n_models = cast(pd.Series, q_df["meta_model"]).nunique()
                print(f"  {q}: {n} samples, {n_models} models")
            print()

    def status(self, mode: str = "per-model"):
        """Show status of fits for a mode.

        Args:
            mode: "per-model", "per-variation", "per-quartile", or "single"
        """
        print(f"\n=== {mode} Fit Status ===\n")

        output_dir = get_output_dir(mode)
        if not output_dir.exists():
            print(f"No fits found for mode '{mode}'")
            print(f"Output directory: {output_dir}")
            return

        # Get expected items
        df = load_all_samples()
        if mode == "per-model":
            expected = [model_id_to_slug(m) for m in sorted(df["meta_model"].unique())]
        elif mode == "per-variation":
            expected = sorted(df["variation"].unique())
        elif mode == "per-quartile":
            expected = QUARTILES
        else:
            print(f"Unknown mode: {mode}")
            return

        done = 0
        pending = 0
        for item_id in expected:
            posterior_path = output_dir / f"{item_id}.npz"
            summary_path = output_dir / f"{item_id}.json"

            if posterior_path.exists() and summary_path.exists():
                with open(summary_path) as f:
                    summary = json.load(f)
                done += 1
                s_mean = summary.get("S_mean", 0)
                print(f"DONE: {item_id} (S={s_mean:.3f})")
            else:
                pending += 1
                print(f"PENDING: {item_id}")

        print(f"\nSummary: {done} done, {pending} pending")

    def quality(self, mode: str = "per-model"):
        """Show quality status for a mode.

        Args:
            mode: "per-model", "per-variation", "per-quartile", or "single"
        """
        print(f"\n=== {mode} Quality Status ===\n")

        quality_file = get_quality_file(mode)
        metadata = load_quality_metadata(quality_file)

        if not metadata:
            print("No quality metadata found.")
            print(f"Quality file: {quality_file}")
            return

        for item_id, info in sorted(metadata.items()):
            quality = info.get("quality", "unknown")
            ts = info.get("timestamp", "unknown")
            print(f"{quality:5} | {item_id} ({ts[:19]})")

        counts = get_quality_summary(metadata)
        print(
            f"\nSummary: full={counts['full']}, fast={counts['fast']}, ultra={counts['ultra']}"
        )

    def fit(
        self,
        model: str | None = None,
        variation: str | None = None,
        quartile: str | None = None,
        all_models: bool = False,
        all_variations: bool = False,
        all_quartiles: bool = False,
        all_singles: bool = False,
        all_combined: bool = False,
        fast: bool = False,
        ultra: bool = False,
        extras: bool = False,
        goal: bool = False,
        unambiguous: bool = False,
        samples: int | None = None,
        warmup: int | None = None,
        chains: int | None = None,
        workers: int = 8,
        delete_everything: bool = False,
    ):
        """Fit pooled regression(s).

        Mode is inferred from flags:
          --model X                  → per-model (1 model × 11 variations)
          --variation Y              → per-variation (23 models × 1 variation)
          --quartile Q               → per-quartile (~6 models × 11 variations)
          --model X --variation Y    → single (1 model × 1 variation)
          --all-models               → 23 per-model fits
          --all-variations           → 11 per-variation fits
          --all-quartiles            → 4 per-quartile fits
          --all-singles              → 253 single fits (1 model × 1 variation each)
          --all-combined             → giant 23×11 regression (253 pair intercepts)

        Quality modes (tracked, only upgrades):
          --ultra                    → 100 samples, 50 warmup, 2 chains
          --fast                     → 500 samples, 250 warmup, 2 chains
          (default)                  → 2000 samples, 1000 warmup, 4 chains
        Test mode (custom MCMC, NOT tracked, saves to {mode}_test/):
          --samples N --warmup N --chains N

        Extra parameters mode:
          --extras                   → Include scenario-specific extra parameters
                                       (excludes derived 'threat', adds goal_value etc.)

        Goal analysis mode:
          --goal                     → Include goal_value_harmonized as a 9-level feature
                                       (none + 8 goal values). Only works with per-model mode.
                                       Maps bidirectional goals to AI's original goal.
                                       Zeros goal_value for email_spam_filter and hiding_reward_hacking.

        Unambiguous subset mode:
          --unambiguous              → Exclude variations with ambiguous misalignment signals:
                                       gpu_decision, hiding_reward_hacking, email_spam_filter, leak-doj.
                                       Only works with --all-models, --all-quartiles, or --model.
                                       Saves to {mode}_unambiguous/.

        Args:
            model: Model ID or comma-separated list
            variation: Variation name or comma-separated list
            quartile: Quartile (q1, q2, q3, q4) or comma-separated list
            all_models: Fit all 23 models (per-model mode)
            all_variations: Fit all 11 variations (per-variation mode)
            all_quartiles: Fit all 4 quartiles (per-quartile mode)
            all_singles: Fit all 253 (model, variation) pairs separately
            all_combined: Fit all 23 models × 11 variations in one regression
            fast: Use fast MCMC (500 samples, 2 chains)
            ultra: Use ultra-fast MCMC (100 samples, 2 chains)
            extras: Include scenario-specific extra parameters
            goal: Include 9-level goal_value_harmonized (per-model mode only)
            unambiguous: Exclude ambiguous variations (gpu_decision, hiding_reward_hacking, email_spam_filter, leak-doj)
            samples: Custom samples (enables test mode)
            warmup: Custom warmup (enables test mode)
            chains: Custom chains (enables test mode)
            workers: Number of parallel workers
            delete_everything: Delete existing posteriors for items being fitted before fitting
        """
        import time

        # Detect test mode (custom MCMC parameters)
        is_test_mode = samples is not None or warmup is not None or chains is not None
        mcmc_override: dict[str, int] | None = None

        if is_test_mode:
            # Test mode: custom MCMC, no quality tracking
            mcmc_override = {
                "samples": samples or 300,
                "warmup": warmup or 200,
                "chains": chains or 2,
            }
            mcmc_mode = None  # Don't use preset modes
            requested_quality = None  # No quality tracking
            print(f"TEST MODE: custom MCMC ({mcmc_override})")
            print(
                "Results will be saved to {mode}_test/ and NOT tracked in quality metadata."
            )
            print()
        elif ultra:
            requested_quality = "ultra"
            mcmc_mode = "ultra"
        elif fast:
            requested_quality = "fast"
            mcmc_mode = "fast"
        else:
            requested_quality = "full"
            mcmc_mode = None

        # Validate --extras usage: only allowed with single-variation modes
        if extras:
            single_variation_mode = (
                all_singles or all_variations or (variation and not all_models)
            )
            if not single_variation_mode:
                print(
                    "Error: --extras can only be used with --all-singles, --all-variations,",
                    file=sys.stderr,
                )
                print("       or --variation (single-variation fits).", file=sys.stderr)
                print(
                    "       Extra parameters are variation-specific and cannot be pooled across variations.",
                    file=sys.stderr,
                )
                sys.exit(1)

        # Validate --goal usage: only allowed with per-model modes
        if goal:
            per_model_mode = all_models or (
                model and not variation and not all_variations
            )
            if not per_model_mode:
                print(
                    "Error: --goal can only be used with --all-models or --model (per-model fits).",
                    file=sys.stderr,
                )
                print(
                    "       Goal analysis requires pooling across all variations for a single model.",
                    file=sys.stderr,
                )
                sys.exit(1)

        # Validate --unambiguous usage: only allowed with per-model or per-quartile modes
        if unambiguous:
            valid_unambiguous_mode = (
                all_models
                or all_quartiles
                or (model and not variation and not all_variations)
                or (quartile and not variation)
            )
            if not valid_unambiguous_mode:
                print(
                    "Error: --unambiguous can only be used with --all-models, --all-quartiles,",
                    file=sys.stderr,
                )
                print(
                    "       --model, or --quartile (pooled fits across variations).",
                    file=sys.stderr,
                )
                print(
                    "       Excludes: gpu_decision, hiding_reward_hacking, email_spam_filter, leak-doj.",
                    file=sys.stderr,
                )
                sys.exit(1)

        # Determine mode and work items
        try:
            mode, work_items = self._build_work_items(
                model=model,
                variation=variation,
                quartile=quartile,
                all_models=all_models,
                all_variations=all_variations,
                all_quartiles=all_quartiles,
                all_singles=all_singles,
                all_combined=all_combined,
                mcmc_mode=mcmc_mode,
                mcmc_override=mcmc_override,
                is_test_mode=is_test_mode,
                use_extras=extras,
                use_goal=goal,
                use_unambiguous=unambiguous,
            )
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            print("Use --help for usage information.", file=sys.stderr)
            sys.exit(1)

        # Determine output mode suffix based on flags
        if is_test_mode:
            output_mode = f"{mode}_test"
        elif unambiguous:
            output_mode = f"{mode}_unambiguous"
        elif goal:
            output_mode = f"{mode}_goal"
        elif extras:
            output_mode = f"{mode}_extras"
        else:
            output_mode = mode

        # Handle delete_everything
        output_dir = get_output_dir(output_mode)
        quality_file = get_quality_file(output_mode)  # Quality file in output dir

        if delete_everything:
            # Only delete files for the items being fitted, not all posteriors
            items_to_delete = [item.item_id for item in work_items]
            print(f"Deleting existing posteriors for {len(items_to_delete)} item(s)...")

            for item_id in items_to_delete:
                npz_path = output_dir / f"{item_id}.npz"
                json_path = output_dir / f"{item_id}.json"

                if npz_path.exists():
                    npz_path.unlink()
                    print(f"Deleted: {npz_path}")
                if json_path.exists():
                    json_path.unlink()
                    print(f"Deleted: {json_path}")

            # Also clear quality metadata for deleted items
            if quality_file.exists():
                metadata_to_clear = load_quality_metadata(quality_file)
                cleared = 0
                for item_id in items_to_delete:
                    if item_id in metadata_to_clear:
                        del metadata_to_clear[item_id]
                        cleared += 1
                if cleared > 0:
                    save_quality_metadata(metadata_to_clear, quality_file)
                    print(f"Cleared quality metadata for {cleared} item(s)")

            print("Delete complete.\n")

        # Load quality metadata (not used in test mode)
        metadata = load_quality_metadata(quality_file)

        # Filter work items based on quality (skip in test mode)
        if is_test_mode:
            # Test mode: fit everything, no quality checking
            filtered_items = work_items
        else:
            # In non-test mode, requested_quality is always set
            assert requested_quality is not None
            filtered_items = []
            skip_reasons: dict[str, list[str]] = {}

            for item in work_items:
                do_fit, reason = should_fit(item.item_id, requested_quality, metadata)
                if do_fit:
                    filtered_items.append(item)
                else:
                    skip_reasons.setdefault(reason, []).append(item.item_id)

            # Show skip summary
            if skip_reasons:
                print("Skipped items:")
                for reason, items in sorted(skip_reasons.items()):
                    print(f"  {reason}: {len(items)} items")
                print()

            if not filtered_items:
                print(
                    "Nothing to fit! All items already at requested quality or higher.",
                    file=sys.stderr,
                )
                print("Use --delete-everything to reset and refit.", file=sys.stderr)
                sys.exit(0)  # Exit 0 since this is expected behavior, not an error

        print(f"\n=== Pooled Fitting ({mode}) ===")
        print(f"Log file: {_log_file}")
        print(f"Output dir: {output_dir}")
        print(
            f"Items to fit: {len(filtered_items)}, Workers: {workers}, Quality: {requested_quality}"
        )
        print()

        # Run fits
        results = []
        completed = 0
        start_time = time.time()

        try:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(fit_single_item_worker, item): item
                    for item in filtered_items
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
                                f"[{completed}/{len(filtered_items)}] {item_id}: SKIPPED ({result.get('reason', '')})"
                            )
                        elif status == "error":
                            print(
                                f"[{completed}/{len(filtered_items)}] {item_id}: ERROR - {result.get('error', '')[:50]}"
                            )
                        else:
                            s = result.get("S_mean", 0)
                            print(
                                f"[{completed}/{len(filtered_items)}] {item_id}: DONE (S={s:.3f}, {elapsed:.0f}s)"
                            )

                            # Update quality metadata (skip in test mode)
                            if not is_test_mode and requested_quality is not None:
                                update_quality_metadata(
                                    item_id, requested_quality, metadata, quality_file
                                )

                    except Exception as e:
                        print(
                            f"[{completed}/{len(filtered_items)}] {item.item_id}: EXCEPTION - {e}"
                        )
                        results.append(
                            {
                                "item_id": item.item_id,
                                "mode": item.mode,
                                "status": "error",
                                "error": str(e),
                            }
                        )

        except KeyboardInterrupt:
            print("\n\nInterrupted! Progress has been saved.")
            print("Run again to continue from where you left off.")

        # Print summary
        print("\n=== Fitting Complete ===\n")
        n_done = sum(1 for r in results if r.get("status") == "done")
        n_error = sum(1 for r in results if r.get("status") == "error")
        n_skipped = sum(1 for r in results if r.get("status") == "skipped")
        print(f"Done: {n_done}, Errors: {n_error}, Skipped: {n_skipped}")

    def _build_work_items(
        self,
        model: str | None,
        variation: str | None,
        quartile: str | None,
        all_models: bool,
        all_variations: bool,
        all_quartiles: bool,
        all_singles: bool,
        all_combined: bool,
        mcmc_mode: str | None,
        mcmc_override: dict[str, int] | None,
        is_test_mode: bool = False,
        use_extras: bool = False,
        use_goal: bool = False,
        use_unambiguous: bool = False,
    ) -> tuple[str, list[FitWorkItem]]:
        """Build work items based on CLI arguments.

        Returns:
            (mode, list of FitWorkItem)

        Raises:
            ValueError: If no valid mode can be determined from arguments.
        """
        from lib.pooled_fitting.extra_params import (
            get_extra_param_variations,
            get_extra_params_for_variation,
        )

        df = load_all_samples()
        all_model_ids = sorted(df["meta_model"].unique().tolist())
        all_variation_names = sorted(df["variation"].unique().tolist())

        # Filter to unambiguous variations if requested
        if use_unambiguous:
            all_variation_names = [
                v
                for v in all_variation_names
                if v not in UNAMBIGUOUS_EXCLUDED_VARIATIONS
            ]
            df = df[~df["variation"].isin(list(UNAMBIGUOUS_EXCLUDED_VARIATIONS))]
            logger.info(
                f"Unambiguous mode: filtered to {len(all_variation_names)} variations "
                f"(excluded: {UNAMBIGUOUS_EXCLUDED_VARIATIONS})"
            )

        work_items = []

        def make_work_item(
            mode: str,
            item_id: str,
            df_filter: dict[str, Any],
            variation_for_extras: str | None = None,
        ) -> FitWorkItem:
            """Helper to create FitWorkItem with consistent settings.

            Args:
                mode: Fitting mode
                item_id: Identifier for this work item
                df_filter: Filter to apply to data
                variation_for_extras: If use_extras and this is set, include
                    extra params for this specific variation
            """
            # Determine output mode suffix
            if is_test_mode:
                output_mode = f"{mode}_test"
            elif use_unambiguous:
                output_mode = f"{mode}_unambiguous"
            elif use_goal:
                output_mode = f"{mode}_goal"
            else:
                output_mode = None

            # Set up extras if requested and we have a specific variation
            extra_params = None
            extra_param_variations = None
            if use_extras and variation_for_extras is not None:
                extra_params = get_extra_params_for_variation(variation_for_extras)
                # Build mapping of which variations implement each extra param
                extra_param_variations = {
                    param: get_extra_param_variations(param) for param in extra_params
                }

            return FitWorkItem(
                mode=mode,
                item_id=item_id,
                df_filter=df_filter,
                mcmc_mode=mcmc_mode,
                mcmc_override=mcmc_override,
                output_mode=output_mode,
                use_extras=use_extras and variation_for_extras is not None,
                extra_params=extra_params,
                extra_param_variations=extra_param_variations,
                use_goal=use_goal,
                exclude_variations=(
                    UNAMBIGUOUS_EXCLUDED_VARIATIONS if use_unambiguous else None
                ),
            )

        # All-singles mode: 253 separate (model, variation) fits
        if all_singles:
            mode = "single"
            for m in all_model_ids:
                for v in all_variation_names:
                    item_id = f"{model_id_to_slug(m)}_{v}"
                    work_items.append(
                        make_work_item(
                            mode,
                            item_id,
                            {"meta_model": m, "variation": v},
                            variation_for_extras=v,  # Single variation -> can use extras
                        )
                    )
            return mode, work_items

        # All-combined mode: giant regression with all 23 models × 11 variations
        if all_combined:
            mode = "all-combined"
            work_items.append(make_work_item(mode, "all", {}))
            return mode, work_items

        # Per-quartile mode
        if quartile or all_quartiles:
            mode = "per-quartile"
            if all_quartiles:
                quartiles = QUARTILES
            else:
                assert quartile is not None
                quartiles = [q.strip() for q in quartile.split(",")]
                # Validate quartile values
                invalid = [q for q in quartiles if q not in QUARTILES]
                if invalid:
                    raise ValueError(
                        f"Invalid quartile(s): {invalid}. Valid values: {QUARTILES}"
                    )

            # Assign quartiles to get model lists
            df["quartile"] = cast(pd.Series, df["meta_model"]).apply(
                lambda m: assign_capability_quartile(m, all_model_ids)
            )

            for q in quartiles:
                q_models = (
                    cast(pd.Series, df[df["quartile"] == q]["meta_model"])
                    .unique()
                    .tolist()
                )
                work_items.append(make_work_item(mode, q, {"meta_model": q_models}))
            return mode, work_items

        # Per-model mode (single model × all variations)
        if (model and not variation and not all_variations) or all_models:
            mode = "per-model"
            if all_models:
                models = all_model_ids
            else:
                assert model is not None
                models = [m.strip() for m in model.split(",")]

            for m in models:
                work_items.append(
                    make_work_item(mode, model_id_to_slug(m), {"meta_model": m})
                )
            return mode, work_items

        # Per-variation mode (all models × single variation)
        if (variation and not model and not all_models) or all_variations:
            mode = "per-variation"
            if all_variations:
                variations = all_variation_names
            else:
                assert variation is not None
                variations = [v.strip() for v in variation.split(",")]

            for v in variations:
                work_items.append(
                    make_work_item(
                        mode,
                        v,
                        {"variation": v},
                        variation_for_extras=v,  # Single variation -> can use extras
                    )
                )
            return mode, work_items

        # Single mode (one model × one variation)
        if model and variation:
            mode = "single"
            models = [m.strip() for m in model.split(",")]
            variations = [v.strip() for v in variation.split(",")]

            for m in models:
                for v in variations:
                    item_id = f"{model_id_to_slug(m)}_{v}"
                    work_items.append(
                        make_work_item(
                            mode,
                            item_id,
                            {"meta_model": m, "variation": v},
                            variation_for_extras=v,  # Single variation -> can use extras
                        )
                    )
            return mode, work_items

        # No valid mode determined from arguments
        raise ValueError(
            "Could not determine fitting mode. Specify one of: "
            "--model, --variation, --quartile, --all-models, --all-variations, "
            "--all-quartiles, --all-singles, or --all-combined"
        )


def main():
    global _log_file
    _log_file = setup_logging()
    fire.Fire(CLI)


if __name__ == "__main__":
    main()
