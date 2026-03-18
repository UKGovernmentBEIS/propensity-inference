"""Configuration constants and shared loaders for transcript analysis."""

import json
import os
from collections import defaultdict
from pathlib import Path

from lib.model_registry import s3_name_to_api_name
from lib.variation_registry import VARIATIONS

# S3 paths — configure S3_MOUNT_POINT to wherever your bucket is accessible.
_S3_ROOT = os.environ.get("PROPENSITY_S3_ROOT", "propensity")
_S3_MOUNT = os.environ.get("S3_MOUNT_POINT", "")
S3_LOGS_BASE = Path(f"{_S3_MOUNT}/{_S3_ROOT}/evals/logs")
S3_LISTING_JSON = S3_LOGS_BASE / "listing.json"
S3_EVAL_AWARENESS_LISTING = S3_LOGS_BASE / "eval_awareness_listing.json"

# Local paths
PAPER_CACHE_SAMPLES = Path("paper_cache/samples")
DEFAULT_SCANS_DIR = Path("scans")

# Config paths
CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs"
TARGETS_PATH = CONFIGS_DIR / "eval_awareness_targets.json"
TOKEN_ESTIMATES_PATH = CONFIGS_DIR / "token_estimates.json"

# Scanner configuration
DEFAULT_CLASSIFIER_MODEL = "openai/gpt-5-2025-08-07"

# Processing defaults
DEFAULT_MAX_TRANSCRIPTS = 25


def load_targets() -> dict[str, dict[str, int]]:
    """Load classification targets from config file.

    Expands the compact JSON format (models + default_target + disabled_models)
    into a full model -> variation -> target count dict.

    Returns:
        Dict of model -> variation -> target count
    """
    if not TARGETS_PATH.exists():
        raise FileNotFoundError(f"Targets file not found: {TARGETS_PATH}")

    with open(TARGETS_PATH) as f:
        data = json.load(f)

    default_target: int = data["default_target"]
    enabled_models: list[str] = data["models"]
    disabled_models: list[str] = data.get("disabled_models", [])

    model_overrides: dict[str, int] = data.get("model_overrides", {})

    targets: dict[str, dict[str, int]] = {}
    for model in enabled_models:
        target: int = model_overrides.get(model, default_target)
        targets[model] = {v: target for v in VARIATIONS}
    for model in disabled_models:
        targets[model] = {v: 0 for v in VARIATIONS}

    return targets


def load_token_estimates() -> dict[str, dict[str, dict[str, int]]]:
    """Load token estimates from config file.

    Returns:
        Dict of model -> variation -> {input_tokens, output_tokens}
    """
    if not TOKEN_ESTIMATES_PATH.exists():
        raise FileNotFoundError(f"Token estimates not found: {TOKEN_ESTIMATES_PATH}")

    with open(TOKEN_ESTIMATES_PATH) as f:
        data = json.load(f)

    return data["token_estimates"]


def load_completed_classifications() -> dict[str, dict[str, set[str]]]:
    """Load completed classifications from S3 listing.

    Returns:
        Dict of model -> variation -> set of classified eval paths
    """
    completed: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    if not S3_EVAL_AWARENESS_LISTING.exists():
        return completed

    with open(S3_EVAL_AWARENESS_LISTING) as f:
        data = json.load(f)

    entries = data["entries"]

    for eval_path in entries:
        # Parse eval path: scenario/variation/version/model/timestamp_task.eval
        parts = eval_path.split("/")
        if len(parts) < 4:
            raise ValueError(
                f"Unexpected eval path format (expected at least 4 parts): {eval_path}"
            )

        scenario = parts[0]
        variation = parts[1]
        model_s3_name = parts[3]

        model_api = s3_name_to_api_name(model_s3_name)
        variation_key = f"{scenario}/{variation}"

        completed[model_api][variation_key].add(eval_path)

    return completed
