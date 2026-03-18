#!/usr/bin/env python3
"""Entropy estimation for propensity scenarios.

Estimates H(Y|X) - the conditional entropy of misalignment given parameters.
This measures the irreducible randomness that cannot be explained by parameter configuration.

Usage:
    uv run scripts/entropy/estimate.py run-samples \
        --model "openai/o4-mini-2025-04-16" \
        --scenario agentic_misalignment_v2 \
        --variation alert \
        --num-samples 500
"""

import hashlib
import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import fire
import numpy as np
from inspect_ai import eval_set, task_with
from inspect_ai.log import EvalLog

from lib.analysis.entropy import binary_entropy
from lib.eval_storage import list_evals, process_eval_logs_parallel, upload_eval
from lib.version_tracking import get_current_version
from scenarios.scenario_registry import SCENARIO_FACTORIES

# Lazy import for DateContext (only needed for gpu_decision_email_assistant)
_DateContext = None


def _get_date_context_class():
    """Lazy import DateContext to avoid circular imports."""
    global _DateContext
    if _DateContext is None:
        from scenarios.gpu_decision_email_assistant.lib.date_utils import DateContext

        _DateContext = DateContext
    return _DateContext


def hydrate_derived_params(params: dict[str, Any], scenario: str) -> dict[str, Any]:
    """Reconstruct derived parameters that don't serialize to JSON.

    Some scenarios have derived parameters (like DateContext objects) that
    become None when serialized to JSON metadata. This function reconstructs
    them from the base parameters.

    Args:
        params: Task parameters loaded from S3 metadata.
        scenario: Scenario name.

    Returns:
        Parameters with derived values reconstructed.
    """
    params = params.copy()

    # gpu_decision_email_assistant: reconstruct date_context from date
    if scenario == "gpu_decision_email_assistant":
        if params.get("date_context") is None and params.get("date"):
            DateContext = _get_date_context_class()
            date_context = DateContext(params["date"])
            params["date_context"] = date_context
            # Also reconstruct other derived params from date_context
            params["date_variables"] = date_context.get_all_variables()
            params["email_timestamps"] = date_context.get_email_timestamps()
            # Reconstruct timestamp if hour/minute/second are available
            if all(k in params for k in ["hour", "minute", "second"]):
                params["timestamp"] = date_context.timestamp(
                    int(params["hour"]), int(params["minute"]), int(params["second"])
                )

    return params


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Always run 29 samples per config (to reach 30 total with original)
SAMPLES_PER_CONFIG = 29


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class ConfigSample:
    """A sample from a parameter configuration."""

    config_hash: str
    task_params: dict[str, Any]
    score: int  # 0 or 1
    model: str


@dataclass
class ConfigStats:
    """Aggregated stats for a configuration."""

    config_hash: str
    task_params: dict[str, Any]
    n_samples: int
    n_successes: int

    @property
    def p_hat(self) -> float:
        return self.n_successes / self.n_samples if self.n_samples > 0 else 0.0


# =============================================================================
# ENTROPY ESTIMATION
# =============================================================================


def empirical_bayes_estimator(
    k_values: np.ndarray, n_values: np.ndarray, n_draws: int = 1000
) -> tuple[float, np.ndarray]:
    """Empirical Bayes entropy estimator with uncertainty quantification.

    Note: lib.analysis.entropy has a simpler version that returns only the point
    estimate. This version returns the full posterior draws for CI computation.

    Fits Beta prior via method of moments, computes posterior distribution of entropy.

    Returns:
        Tuple of (point estimate, array of n_draws samples from posterior).
    """
    p_hat = k_values / n_values
    mean_p = np.mean(p_hat)
    var_p = np.var(p_hat)

    # Fit Beta prior
    if var_p < 1e-8:
        alpha, beta_param = 1.0, 1.0
    else:
        s = mean_p * (1 - mean_p) / var_p - 1
        if s <= 0:
            alpha, beta_param = 1.0, 1.0
        else:
            alpha = max(0.1, min(mean_p * s, 100.0))
            beta_param = max(0.1, min((1 - mean_p) * s, 100.0))

    # Sample from joint posterior of all config entropies
    # For each draw: sample p_i for each config, compute H_i, average
    n_configs = len(k_values)
    H_draws = np.zeros(n_draws)

    for draw in range(n_draws):
        config_entropies = np.zeros(n_configs)
        for i, (k, n) in enumerate(zip(k_values, n_values)):
            post_a = alpha + k
            post_b = beta_param + (n - k)
            p_sample = np.random.beta(post_a, post_b)
            config_entropies[i] = binary_entropy(p_sample)
        H_draws[draw] = np.mean(config_entropies)

    return float(np.mean(H_draws)), H_draws


# =============================================================================
# DATA LOADING
# =============================================================================


HASH_EXCLUDE_KEYS = {
    "entropy_sample_idx",
    "entropy_config_hash",
    "entropy_estimation",
    "entropy_source",
    "_entropy_config_hash",
    "_entropy_estimation",
    "_entropy_source",
}


def hash_params(params: dict[str, Any]) -> str:
    """Create stable hash of parameters, excluding entropy metadata."""
    filtered = {k: v for k, v in params.items() if k not in HASH_EXCLUDE_KEYS}
    json_str = json.dumps(filtered, sort_keys=True, default=str)
    return hashlib.md5(json_str.encode()).hexdigest()[:16]


def extract_score(sample) -> int | None:
    """Extract 0/1 score from a sample."""
    if not sample.scores:
        return None
    score_obj = next(iter(sample.scores.values()))
    val = score_obj.value
    if val in ("C", "CORRECT", 1, 1.0, "1"):
        return 1
    elif val in ("I", "INCORRECT", 0, 0.0, "0"):
        return 0
    return None


def extract_samples_from_log(
    log: EvalLog, model_filter: str | None = None
) -> list[ConfigSample]:
    """Extract ConfigSamples from an eval log."""
    if model_filter and model_filter not in log.eval.model:
        return []

    meta = log.eval.metadata or {}
    task_params = meta.get("task_params", {})

    # Try sample metadata if not in eval metadata
    if not task_params and log.samples and log.samples[0].metadata:
        task_params = log.samples[0].metadata.get("task_params", {})

    if not task_params or not log.samples:
        return []

    config_hash = hash_params(task_params)
    samples = []

    for sample in log.samples:
        score = extract_score(sample)
        if score is not None:
            samples.append(
                ConfigSample(
                    config_hash=config_hash,
                    task_params=task_params,
                    score=score,
                    model=log.eval.model,
                )
            )

    return samples


def load_samples_from_s3(
    model: str,
    scenario: str,
    variation: str,
    sample_n: int | None = None,
) -> list[ConfigSample]:
    """Load samples from S3 structured storage."""
    import random

    from lib.eval_storage import get_bucket

    bucket = get_bucket()
    min_version = "0.0.0"
    logger.info(f"Querying S3: {scenario}/{variation}/{model} (>= {min_version})")

    paths = list(
        list_evals(
            scenario=scenario, variation=variation, model=model, min_version=min_version
        )
    )
    logger.info(f"Found {len(paths)} eval files")

    if not paths:
        return []

    # Sample if requested
    if sample_n and len(paths) > sample_n:
        paths = random.sample(paths, sample_n)

    # Read in parallel
    s3_uris = [p.s3_uri(bucket) for p in paths]

    def extract(log: EvalLog) -> list[ConfigSample] | None:
        result = extract_samples_from_log(log)
        return result if result else None

    nested = process_eval_logs_parallel(s3_uris, extract, header_only=False)
    samples = [s for batch in nested for s in batch]

    logger.info(f"Loaded {len(samples)} samples from S3")
    return samples


def aggregate_by_config(samples: list[ConfigSample]) -> dict[str, ConfigStats]:
    """Aggregate samples by config hash."""
    by_config: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "k": 0, "params": None}
    )

    for s in samples:
        by_config[s.config_hash]["n"] += 1
        by_config[s.config_hash]["k"] += s.score
        if by_config[s.config_hash]["params"] is None:
            by_config[s.config_hash]["params"] = s.task_params

    return {
        h: ConfigStats(
            config_hash=h, task_params=d["params"], n_samples=d["n"], n_successes=d["k"]
        )
        for h, d in by_config.items()
    }


def _get_existing_entropy_config_hashes(
    model: str,
    scenario: str,
    variation: str,
) -> set[str]:
    """Get config hashes that already have entropy samples in S3.

    Returns:
        Set of config hashes that already have entropy data.
    """
    from lib.eval_storage import get_bucket, read_eval_logs_parallel

    bucket = get_bucket()
    min_version = "0.0.0"

    # Query entropy files specifically
    paths = list(
        list_evals(
            scenario=scenario,
            variation=variation,
            model=model,
            min_version=min_version,
            subdir="entropy",  # Only get entropy samples
        )
    )

    if not paths:
        return set()

    # Read files to extract config hashes from metadata
    s3_uris = [p.s3_uri(bucket) for p in paths]
    log_results = read_eval_logs_parallel(s3_uris, header_only=False, max_workers=32)

    config_hashes: set[str] = set()
    for _uri, log in log_results:
        if log is None:
            continue
        # Check sample metadata for entropy_config_hash
        for sample in log.samples or []:
            sample_meta = sample.metadata or {}
            config_hash = sample_meta.get("entropy_config_hash")
            if config_hash:
                config_hashes.add(config_hash)

    return config_hashes


# =============================================================================
# CLI
# =============================================================================


class EntropyEstimator:
    """CLI for entropy estimation."""

    def run_samples(
        self,
        model: str,
        scenario: str,
        variation: str,
        num_samples: int = 500,
        output_dir: str = "logs/entropy_estimation",
        upload_to_s3: bool = True,
        dry_run: bool = False,
    ):
        """Run new samples for entropy estimation.

        Selects random configs and runs SAMPLES_PER_CONFIG (29) additional samples each.
        """
        n_configs = num_samples // SAMPLES_PER_CONFIG
        if n_configs == 0:
            logger.error(
                f"num_samples={num_samples} too small (need >= {SAMPLES_PER_CONFIG})"
            )
            return

        logger.info(
            f"Budget: {n_configs} configs × {SAMPLES_PER_CONFIG} samples = {n_configs * SAMPLES_PER_CONFIG}"
        )

        # Load existing samples from S3
        samples = load_samples_from_s3(model, scenario, variation, sample_n=n_configs)

        if not samples:
            logger.error("No samples found")
            return

        import random

        config_stats = aggregate_by_config(samples)

        # Exclude configs that already have entropy samples
        existing_entropy_hashes = _get_existing_entropy_config_hashes(
            model, scenario, variation
        )
        if existing_entropy_hashes:
            logger.info(
                f"Found {len(existing_entropy_hashes)} configs with existing entropy samples, excluding"
            )
            config_stats = {
                h: s
                for h, s in config_stats.items()
                if h not in existing_entropy_hashes
            }
            if not config_stats:
                logger.error("All configs already have entropy samples!")
                return

        if len(config_stats) < n_configs:
            n_configs = len(config_stats)

        selected = random.sample(list(config_stats.values()), n_configs)
        logger.info(
            f"Selected {len(selected)} new configs (excluding existing entropy)"
        )

        # Validate that recomputed hashes match stored hashes
        hash_mismatches = []
        for config in selected:
            recomputed_hash = hash_params(config.task_params)
            if recomputed_hash != config.config_hash:
                hash_mismatches.append(
                    {
                        "stored": config.config_hash,
                        "recomputed": recomputed_hash,
                        "params": config.task_params,
                    }
                )

        if hash_mismatches:
            logger.error(f"Hash mismatch for {len(hash_mismatches)} configs!")
            for mismatch in hash_mismatches[:3]:  # Show first 3
                logger.error(
                    f"  Stored: {mismatch['stored']}, Recomputed: {mismatch['recomputed']}"
                )
            raise ValueError(
                f"Config hash mismatch: {len(hash_mismatches)} configs have different hashes when recomputed. "
                "This indicates entropy metadata keys are leaking into task_params. "
                "Check HASH_EXCLUDE_KEYS in estimate_entropy.py."
            )

        # Get scenario
        if scenario not in SCENARIO_FACTORIES:
            logger.error(f"Unknown scenario: {scenario}")
            return

        scenario_def = SCENARIO_FACTORIES[scenario]()

        # Create output directory
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        run_dir = Path(output_dir) / f"entropy_{scenario}_{variation}_{timestamp}"
        run_dir.mkdir(parents=True, exist_ok=True)

        # Create tasks with standard metadata (same as run_scenarios.py)
        version = get_current_version()
        user_name = os.environ.get("S3_USER", "unknown")

        tasks = []
        for config in selected:
            params = config.task_params.copy()
            params = hydrate_derived_params(params, scenario)
            for i in range(SAMPLES_PER_CONFIG):
                task = scenario_def.params_to_task(params)

                # Standard metadata (matches run_scenarios._enrich_task_metadata_inplace)
                standard_metadata = {
                    "task_params": params,
                    "scenario_name": scenario,
                    "variation_name": variation,
                    "version": version,
                    "user_name": user_name,
                    "entropy_config_hash": config.config_hash,
                }

                # Add to sample metadata
                for sample in task.dataset:
                    sample.metadata = sample.metadata or {}
                    sample.metadata.update(standard_metadata)

                # Add to task metadata
                if not task.metadata:
                    task.metadata = {}
                task.metadata.update(standard_metadata)

                hash_suffix = hashlib.sha3_256(
                    json.dumps(
                        {"h": config.config_hash, "i": i}, sort_keys=True
                    ).encode()
                ).hexdigest()[:16]
                task = task_with(
                    task=task, dataset=task.dataset, name=f"{task.name}_{hash_suffix}"
                )
                tasks.append(task)

        logger.info(f"Created {len(tasks)} tasks")

        if dry_run:
            print(f"DRY RUN: {len(tasks)} tasks, output: {run_dir}")
            return

        # Run
        logs = eval_set(
            tasks, model=model, log_dir=str(run_dir), max_tasks=50, max_connections=50
        )
        logger.info(f"Completed {len(logs)} evaluations")

        # Upload
        if upload_to_s3:
            version = get_current_version()
            for eval_file in run_dir.glob("*.eval"):
                upload_eval(
                    eval_file, scenario, variation, version, model, subdir="entropy"
                )
            logger.info("Uploaded to S3")

        # Estimate entropy from the log files we just generated
        # Read from disk rather than relying on eval_set return values
        from inspect_ai.log import read_eval_log

        all_samples: list[ConfigSample] = []
        eval_files = list(run_dir.glob("*.eval"))
        logger.info(f"Reading {len(eval_files)} eval files from {run_dir}")

        for eval_file in eval_files:
            try:
                log = read_eval_log(str(eval_file))
                all_samples.extend(extract_samples_from_log(log, model_filter=None))
            except Exception as e:
                logger.warning(f"Failed to read {eval_file.name}: {e}")

        if not all_samples:
            logger.warning("No samples extracted from logs")
            return None

        # Aggregate by config and filter to configs with enough samples
        config_stats = aggregate_by_config(all_samples)
        filtered = {
            h: s for h, s in config_stats.items() if s.n_samples >= SAMPLES_PER_CONFIG
        }

        if not filtered:
            logger.warning(
                f"No configs with >= {SAMPLES_PER_CONFIG} samples. "
                f"Total configs: {len(config_stats)}"
            )
            return None

        # Compute entropy estimate
        k_values = np.array([s.n_successes for s in filtered.values()])
        n_values = np.array([s.n_samples for s in filtered.values()])
        total_n = sum(s.n_samples for s in filtered.values())
        total_k = sum(s.n_successes for s in filtered.values())

        H_est, H_draws = empirical_bayes_estimator(k_values, n_values)
        base_rate = total_k / total_n
        H_ci = (float(np.percentile(H_draws, 2.5)), float(np.percentile(H_draws, 97.5)))

        print(f"\n{'=' * 60}")
        print("ENTROPY ESTIMATION RESULTS")
        print(f"{'=' * 60}")
        print(f"Configs with {SAMPLES_PER_CONFIG}+ samples: {len(filtered)}")
        print(f"Total samples: {total_n}")
        print(f"Base rate: {base_rate:.1%}")
        print(
            f"Estimated H(Y|X): {H_est:.4f} bits  95% CI: [{H_ci[0]:.4f}, {H_ci[1]:.4f}]"
        )
        print(f"{'=' * 60}")

        # Save entropy summary to local cache (append to existing data)
        cache_dir = Path("paper_cache/entropy_samples")
        cache_dir.mkdir(parents=True, exist_ok=True)
        model_slug = model.replace("/", "_").replace(":", "_")
        cache_file = cache_dir / f"{model_slug}_{variation}.json"

        # Load existing data if present
        existing_k = []
        existing_n = []
        if cache_file.exists():
            with open(cache_file) as f:
                existing = json.load(f)
                existing_k = existing.get("k_values", [])
                existing_n = existing.get("n_values", [])
            logger.info(f"Loaded {len(existing_k)} existing configs from cache")

        # Merge with new data
        combined_k = existing_k + k_values.tolist()
        combined_n = existing_n + n_values.tolist()

        # Recompute entropy from combined data
        combined_k_arr = np.array(combined_k)
        combined_n_arr = np.array(combined_n)
        combined_total_n = int(np.sum(combined_n_arr))
        combined_total_k = int(np.sum(combined_k_arr))
        combined_H_est, combined_H_draws = empirical_bayes_estimator(
            combined_k_arr, combined_n_arr
        )
        combined_base_rate = combined_total_k / combined_total_n
        combined_H_ci = (
            float(np.percentile(combined_H_draws, 2.5)),
            float(np.percentile(combined_H_draws, 97.5)),
        )

        entropy_summary = {
            "model": model,
            "scenario": scenario,
            "variation": variation,
            "k_values": combined_k,
            "n_values": combined_n,
            "H_Y_given_X": combined_H_est,
            "H_Y_given_X_ci": combined_H_ci,
            "base_rate": combined_base_rate,
            "n_configs": len(combined_k),
            "total_samples": combined_total_n,
        }

        with open(cache_file, "w") as f:
            json.dump(entropy_summary, f, indent=2)
        logger.info(
            f"Saved entropy summary to {cache_file} ({len(combined_k)} total configs)"
        )

        # Upload entropy summary to S3
        if upload_to_s3:
            import boto3

            bucket = os.environ.get("S3_BUCKET")
            if bucket:
                s3_key = f"{os.environ.get('PROPENSITY_S3_ROOT', 'propensity')}/paper_cache/entropy_samples/{model_slug}_{variation}.json"
                s3 = boto3.client("s3")
                s3.upload_file(str(cache_file), bucket, s3_key)
                logger.info(f"Uploaded entropy summary to s3://{bucket}/{s3_key}")
            else:
                logger.warning(
                    "S3_BUCKET not set, skipping S3 upload of entropy summary"
                )

        return {"H_est": H_est, "n_configs": len(filtered), "total_samples": total_n}

    def recompute_from_s3(
        self,
        model: str,
        scenario: str,
        variation: str,
        upload_to_s3: bool = True,
    ):
        """Recompute entropy estimate from all entropy evals in S3.

        This aggregates all entropy eval files for a (model, scenario, variation)
        and recomputes the entropy estimate, updating the local cache.
        """
        from lib.eval_storage import get_bucket, read_eval_logs_parallel

        bucket = get_bucket()
        min_version = "0.0.0"

        # Get all entropy files
        paths = list(
            list_evals(
                scenario=scenario,
                variation=variation,
                model=model,
                min_version=min_version,
                subdir="entropy",
            )
        )

        if not paths:
            logger.error(f"No entropy files found for {model} / {variation}")
            return

        logger.info(f"Found {len(paths)} entropy eval files in S3")

        # Read all files
        s3_uris = [p.s3_uri(bucket) for p in paths]
        log_results = read_eval_logs_parallel(
            s3_uris, header_only=False, max_workers=32
        )

        # Extract samples
        all_samples: list[ConfigSample] = []
        for _uri, log in log_results:
            if log is None:
                continue
            all_samples.extend(extract_samples_from_log(log, model_filter=None))

        logger.info(f"Extracted {len(all_samples)} samples from entropy files")

        if not all_samples:
            logger.error("No samples extracted")
            return

        # Aggregate by config
        config_stats = aggregate_by_config(all_samples)
        logger.info(f"Found {len(config_stats)} unique configs")

        # Filter to configs with enough samples
        filtered = {
            h: s for h, s in config_stats.items() if s.n_samples >= SAMPLES_PER_CONFIG
        }

        if not filtered:
            logger.warning(f"No configs with >= {SAMPLES_PER_CONFIG} samples")
            return

        # Compute entropy estimate
        k_values = np.array([s.n_successes for s in filtered.values()])
        n_values = np.array([s.n_samples for s in filtered.values()])
        total_n = sum(s.n_samples for s in filtered.values())
        total_k = sum(s.n_successes for s in filtered.values())

        H_est, H_draws = empirical_bayes_estimator(k_values, n_values)
        base_rate = total_k / total_n
        H_ci = (float(np.percentile(H_draws, 2.5)), float(np.percentile(H_draws, 97.5)))

        print(f"\n{'=' * 60}")
        print("ENTROPY ESTIMATION RESULTS (from S3)")
        print(f"{'=' * 60}")
        print(f"Configs with {SAMPLES_PER_CONFIG}+ samples: {len(filtered)}")
        print(f"Total samples: {total_n}")
        print(f"Base rate: {base_rate:.1%}")
        print(
            f"Estimated H(Y|X): {H_est:.4f} bits  95% CI: [{H_ci[0]:.4f}, {H_ci[1]:.4f}]"
        )
        print(f"{'=' * 60}")

        # Save entropy summary
        entropy_summary = {
            "model": model,
            "scenario": scenario,
            "variation": variation,
            "k_values": k_values.tolist(),
            "n_values": n_values.tolist(),
            "H_Y_given_X": H_est,
            "H_Y_given_X_ci": H_ci,
            "base_rate": base_rate,
            "n_configs": len(filtered),
            "total_samples": int(total_n),
        }

        cache_dir = Path("paper_cache/entropy_samples")
        cache_dir.mkdir(parents=True, exist_ok=True)
        model_slug = model.replace("/", "_").replace(":", "_")
        cache_file = cache_dir / f"{model_slug}_{variation}.json"
        with open(cache_file, "w") as f:
            json.dump(entropy_summary, f, indent=2)
        logger.info(f"Saved entropy summary to {cache_file}")

        # Upload to S3
        if upload_to_s3:
            import boto3

            bucket_name = os.environ.get("S3_BUCKET")
            if bucket_name:
                s3_key = f"{os.environ.get('PROPENSITY_S3_ROOT', 'propensity')}/paper_cache/entropy_samples/{model_slug}_{variation}.json"
                s3 = boto3.client("s3")
                s3.upload_file(str(cache_file), bucket_name, s3_key)
                logger.info(f"Uploaded to s3://{bucket_name}/{s3_key}")

        return {"H_est": H_est, "n_configs": len(filtered), "total_samples": total_n}


def main():
    fire.Fire(EntropyEstimator)


if __name__ == "__main__":
    main()
