"""Dynamic configuration builder for pooled regression fitting.

Builds HiBayES AnalysisConfig objects dynamically based on:
- Which (model, variation) pairs are in the data (for intercepts)
- All 12 parameters (always included, zeroing handles unimplemented)
- Optional extra scenario-specific parameters (with --extras flag)

Why _DUMMY_ appears in all category lists: See lib/analysis/effect_coding.py
"""

import copy
import logging
from typing import Any

from hibayes.analysis import AnalysisConfig

from lib.paper_style import ALL_PARAMS, NON_STRATEGIC_PARAMS, STRATEGIC_PARAMS

logger = logging.getLogger(__name__)

# Core parameters that are excluded when using extras
# (because extras provide more specific versions)
EXCLUDED_WHEN_EXTRAS = {
    "threat"
}  # Replaced by urgency_type, threat_type, variant_severity etc.

# All variations for category order
ALL_VARIATION_NAMES = [
    "alert",
    "leak-starsentinel",
    "leak-doj",
    "email_spam_filter",
    "gpu_decision",
    "hiding_reward_hacking",
    "threat",
    "enhancement",
    "expansion",
    "classification",
    "summarization",
]

# Category orders for all parameters
PARAM_CATEGORY_ORDER: dict[str, list[str]] = {
    "goal_present": ["true", "false", "_DUMMY_"],
    "goal_conflict": ["true", "false", "_DUMMY_"],
    "threat": ["replacement", "other", "none", "_DUMMY_"],
    "cot_privacy": [
        "discarded",
        "not_visible",
        "not_accessible_actions",
        "saved_not_accessible",
        "logged_not_accessible",
        "none",
        "saved_visible",
        "monitored_visible",
        "_DUMMY_",
    ],
    "action_oversight": ["none", "oversight", "_DUMMY_"],
    "action_efficacy_binary": ["effective", "not_effective", "_DUMMY_"],
    "cot_tag": [
        "thinking",
        "reasoning",
        "scratchpad",
        "scratchpad_reasoning",
        "planning",
        "chain_of_thought",
        "cot_lower",
        "cot_upper",
        "_DUMMY_",
    ],
    "reasoning_instructions": [
        "strategic_goals",
        "strategic_plan",
        "consider_context",
        "write_thoughts",
        "cot_performance",
        "none",
        "_DUMMY_",
    ],
    "independence": [
        "strong_independence",
        "encourage_independence",
        "neutral",
        "encourage_consultation",
        "require_consultation",
        "_DUMMY_",
    ],
    "anti_misalignment": [
        "encourage_creativity",
        "neutral",
        "avoid_unwanted",
        "avoid_misalignment_simple",
        "avoid_misalignment_detailed",
        "_DUMMY_",
    ],
    "filler_richness": ["full", "minimal", "_DUMMY_"],
    "date_month_year": [
        "Jul 2024",
        "Oct 2024",
        "Jan 2025",
        "Apr 2025",
        "Jul 2025",
        "Oct 2025",
        "Jan 2026",
        "Apr 2026",
        "_DUMMY_",
    ],
}

# Category order for goal_value_harmonized (used with --goal flag)
# "none" is the reference category (first position for effect coding)
GOAL_VALUE_CATEGORY_ORDER = [
    "none",  # Reference category: no goal applicable
    "america",
    "global",
    "safety",
    "acceleration",
    "ethical",
    "pragmatic",
    "individualism",
    "collectivism",
    "_DUMMY_",
]


def build_analysis_config(
    pairs_in_data: list[str],
    extra_params: dict[str, list[str]] | None = None,
    use_extras: bool = False,
    use_goal: bool = False,
) -> tuple[dict[str, Any], AnalysisConfig]:
    """Build HiBayES AnalysisConfig dynamically.

    Args:
        pairs_in_data: List of "model_variation" pair identifiers in the data.
            Each pair gets an independent intercept with N(-3, 3²) prior.
        extra_params: Dict mapping extra param name -> list of categories.
            Only used if use_extras=True.
        use_extras: Whether to include extra scenario-specific parameters.
            When True, excludes 'threat' from core params (replaced by specifics).
            [NOTE] Both use_extras and extra_params are checked because use_extras
            is the flag and extra_params provides the actual categories. Could be
            simplified but works as-is.
        use_goal: Whether to include goal_value_harmonized as a feature.
            When True, adds 9-level goal_value (none + 8 goals) to the model.
            [NOTE] Having "none" as a category when goal_present=false creates an
            implicit interaction: the model captures how goal_value affects outcomes
            only when a goal is present (for better or worse).

    Returns:
        Tuple of (full_config_dict, AnalysisConfig)
    """
    # Build categorical features list
    categorical_features = []
    category_order: dict[str, list[str]] = {}

    # Add pair intercepts - each pair gets an independent N(-3, 3²) intercept
    categorical_features.append("model_variation")
    category_order["model_variation"] = sorted(pairs_in_data) + ["_DUMMY_"]
    logger.info(f"Adding model_variation intercepts: {len(pairs_in_data)} pairs")

    # Determine which core params to include
    core_params = ALL_PARAMS
    if use_extras:
        core_params = [p for p in ALL_PARAMS if p not in EXCLUDED_WHEN_EXTRAS]
        logger.info(f"Excluding core params for extras mode: {EXCLUDED_WHEN_EXTRAS}")

    # Add core parameters
    for param in core_params:
        categorical_features.append(param)
        category_order[param] = PARAM_CATEGORY_ORDER[param]

    # Add extra parameters if provided
    if use_extras and extra_params:
        for param, categories in extra_params.items():
            if param not in categorical_features:  # Avoid duplicates
                categorical_features.append(param)
                category_order[param] = categories
                logger.info(
                    f"Adding extra param: {param} with {len(categories) - 1} categories"
                )

    # Add goal_value_harmonized if requested (--goal flag)
    if use_goal:
        categorical_features.append("goal_value_harmonized")
        category_order["goal_value_harmonized"] = GOAL_VALUE_CATEGORY_ORDER
        logger.info(
            f"Adding goal_value_harmonized: {len(GOAL_VALUE_CATEGORY_ORDER) - 1} categories "
            f"(reference: 'none')"
        )

    # Build the config dict
    config_dict = _build_config_dict(
        categorical_features,
        category_order,
        use_extras=use_extras,
        use_goal=use_goal,
    )

    # Parse into AnalysisConfig
    analysis_config = AnalysisConfig.from_dict(config_dict)

    return config_dict, analysis_config


def _build_config_dict(
    categorical_features: list[str],
    category_order: dict[str, list[str]],
    use_extras: bool = False,
    use_goal: bool = False,
) -> dict[str, Any]:
    """Build the full config dictionary.

    Args:
        categorical_features: List of feature names to include
        category_order: Dict mapping feature -> list of category values
        use_extras: Whether extras mode is active
        use_goal: Whether goal mode is active (adds goal_value_harmonized)
    """
    # Determine which features go in each model
    # All models include model_variation (pair intercepts) + their respective parameters
    if use_extras:
        strategic_params = [
            p for p in STRATEGIC_PARAMS if p not in EXCLUDED_WHEN_EXTRAS
        ]
        non_strategic_params = list(NON_STRATEGIC_PARAMS)
    else:
        strategic_params = list(STRATEGIC_PARAMS)
        non_strategic_params = list(NON_STRATEGIC_PARAMS)

    strategic_main_effects = ["model_variation"] + strategic_params
    non_strategic_main_effects = ["model_variation"] + non_strategic_params

    # Combined model uses all features (model_variation is already first)
    combined_main_effects = list(categorical_features)
    # Trivial model uses only intercepts (no parameter effects)
    intercept_features = ["model_variation"]

    # [NOTE] This config dict structure is HiBayES's expected format. We build it
    # programmatically here for flexibility rather than using YAML files.
    config = {
        # Data loader (minimal - data is passed directly)
        # [NOTE] "data is passed directly" means we don't load from files; instead,
        # the DataFrame is passed to process_data() in core.py. These paths are
        # placeholders required by HiBayES schema but aren't used.
        "data_loader": {
            "paths": {
                "files_to_process": [],
                "cache_path": None,
                "output_dir": "./analysis_output",
            },
            "extractors": {
                "path": ["lib/hibayes_extractors.py"],
                "enabled": [
                    "base_extractor",
                    "propensity_extractor",
                    "propensity_score_extractor",
                    "n_total_extractor",
                ],
            },
        },
        # Data processing
        "data_process": {
            "path": ["lib/hibayes_extractors.py"],
            "processors": [
                {
                    "extract_observed_feature": {"feature_name": "score"}
                },  # [NOTE] "score" rather tham "meta_score", since weighting.py converts this.
                {
                    "extract_features": {
                        "categorical_features": categorical_features,
                        "interactions": False,
                        "effect_coding_for_main_effects": True,
                        "category_order": category_order,
                    }
                },
                "add_n_total_feature",
            ],
        },
        # Models - using custom model with per-variable priors:
        # - model_variation (pair intercepts): N(-3, 3²)
        # - all parameters: N(0, 1)
        "model": {
            "models": [
                # Model 1: Strategic parameters only
                {
                    "name": "linear_group_binomial_pervar",
                    "config": {
                        "main_effects": strategic_main_effects,
                        "interactions": [],
                        "prior_main_effects_loc": {"model_variation": -3.0},
                        "prior_main_effects_scale": {"model_variation": 3.0},
                        "tag": "strategic_only",
                        # [NOTE] These are default MCMC settings for full quality.
                        # They get overwritten by get_reduced_mcmc_config() when
                        # --fast or --ultra flags are used (which is quite spaghetty).
                        "fit": {
                            "method": "NUTS",
                            "samples": 2000,
                            "warmup": 1000,
                            "chains": 4,
                            "seed": 42,
                            "target_accept": 0.95,
                            "init_strategy": "median",
                        },
                    },
                },
                # Model 2: Non-strategic parameters only
                {
                    "name": "linear_group_binomial_pervar",
                    "config": {
                        "main_effects": non_strategic_main_effects,
                        "interactions": [],
                        "prior_main_effects_loc": {"model_variation": -3.0},
                        "prior_main_effects_scale": {"model_variation": 3.0},
                        "tag": "non_strategic_only",
                        "fit": {
                            "method": "NUTS",
                            "samples": 2000,
                            "warmup": 1000,
                            "chains": 4,
                            "seed": 42,
                            "target_accept": 0.95,
                            "init_strategy": "median",
                        },
                    },
                },
                # Model 3: Combined (all parameters)
                {
                    "name": "linear_group_binomial_pervar",
                    "config": {
                        "main_effects": combined_main_effects,
                        "interactions": [],
                        "prior_main_effects_loc": {"model_variation": -3.0},
                        "prior_main_effects_scale": {"model_variation": 3.0},
                        "tag": "combined",
                        "fit": {
                            "method": "NUTS",
                            "samples": 2000,
                            "warmup": 1000,
                            "chains": 4,
                            "seed": 42,
                            "target_accept": 0.95,
                            "init_strategy": "median",
                        },
                    },
                },
                # Model 4: Trivial baseline (intercepts only, no parameters)
                # Used for proper RQ1 computation with Bayesian baseline
                {
                    "name": "linear_group_binomial_pervar",
                    "config": {
                        "main_effects": intercept_features,
                        "interactions": [],
                        "prior_main_effects_loc": {"model_variation": -3.0},
                        "prior_main_effects_scale": {"model_variation": 3.0},
                        "tag": "trivial",
                        "fit": {
                            "method": "NUTS",
                            "samples": 2000,
                            "warmup": 1000,
                            "chains": 4,
                            "seed": 42,
                            "target_accept": 0.95,
                            "init_strategy": "median",
                        },
                    },
                },
            ],
        },
        # Convergence diagnostics (using HiBayES defaults 1.01, 1000 and 0 for r_hat, ess_bulk and divergences_)
        "check": {
            "checkers": ["r_hat", "ess_bulk", "divergences", "waic"],
        },
        # Platform
        "platform": {
            "chain_method": "parallel",
        },
        # Parameter classification (for reference, not used by HiBayES)
        "parameter_classification": {
            "strategic": list(STRATEGIC_PARAMS),
            "non_strategic": list(NON_STRATEGIC_PARAMS),
        },
    }

    return config


def get_reduced_mcmc_config(
    config_dict: dict[str, Any],
    mode: str = "fast",
) -> dict[str, Any]:
    """Create config with reduced MCMC samples.

    Args:
        config_dict: Full config dictionary
        mode: "ultra" (300 samples, 2 chains) or "fast" (500 samples, 2 chains)

    Returns:
        Modified config dictionary
    """
    config = copy.deepcopy(config_dict)

    if mode == "ultra":
        samples, warmup, chains = 100, 50, 2
    elif mode == "fast":
        samples, warmup, chains = 500, 250, 2
    else:
        raise ValueError(f"Unknown mode: {mode}")

    for model_spec in config["model"]["models"]:
        model_spec["config"]["fit"]["samples"] = samples
        model_spec["config"]["fit"]["warmup"] = warmup
        model_spec["config"]["fit"]["chains"] = chains

    logger.info(
        f"Using {mode} MCMC: {samples} samples, {warmup} warmup, {chains} chains"
    )

    return config


def apply_mcmc_override(
    config_dict: dict[str, Any],
    samples: int,
    warmup: int,
    chains: int,
) -> dict[str, Any]:
    """Apply custom MCMC settings (for testing).

    Unlike get_reduced_mcmc_config(), this applies arbitrary values
    rather than preset modes. Used for quick iteration during development.

    Args:
        config_dict: Full config dictionary
        samples: Number of posterior samples
        warmup: Number of warmup steps
        chains: Number of MCMC chains

    Returns:
        Modified config dictionary (deep copy)
    """
    config = copy.deepcopy(config_dict)

    for model_spec in config["model"]["models"]:
        model_spec["config"]["fit"]["samples"] = samples
        model_spec["config"]["fit"]["warmup"] = warmup
        model_spec["config"]["fit"]["chains"] = chains

    logger.info(
        f"Using custom MCMC override: {samples} samples, {warmup} warmup, {chains} chains"
    )

    return config


def get_categorical_features_from_config(config_dict: dict[str, Any]) -> list[str]:
    """Extract categorical features list from config dictionary."""
    if "data_process" not in config_dict:
        raise ValueError("Config missing 'data_process' key")
    if "processors" not in config_dict["data_process"]:
        raise ValueError("Config missing 'data_process.processors' key")

    for proc in config_dict["data_process"]["processors"]:
        if isinstance(proc, dict) and "extract_features" in proc:
            if "categorical_features" not in proc["extract_features"]:
                raise ValueError(
                    "Config 'extract_features' missing 'categorical_features' key"
                )
            return proc["extract_features"]["categorical_features"]

    raise ValueError("Config has no 'extract_features' processor")


def get_category_order_from_config(config_dict: dict[str, Any]) -> dict[str, list[str]]:
    """Extract category order dict from config dictionary."""
    if "data_process" not in config_dict:
        raise ValueError("Config missing 'data_process' key")
    if "processors" not in config_dict["data_process"]:
        raise ValueError("Config missing 'data_process.processors' key")

    for proc in config_dict["data_process"]["processors"]:
        if isinstance(proc, dict) and "extract_features" in proc:
            if "category_order" not in proc["extract_features"]:
                raise ValueError(
                    "Config 'extract_features' missing 'category_order' key"
                )
            return proc["extract_features"]["category_order"]

    raise ValueError("Config has no 'extract_features' processor")
