"""Type definitions for propensity analysis.

This module contains all dataclasses used throughout the analysis pipeline.
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# =============================================================================
# RQ1 Metric Types
# =============================================================================


@dataclass
class RQ1Results:
    """Results from RQ1 analysis with proper Bayesian uncertainty.

    RQ1 measures the proportion of explained variance attributable to
    strategic vs non-strategic parameters:
        RQ1 = (A + C - B) / (2C)

    Where:
        A = Strategic model improvement over trivial baseline (intercepts-only)
        B = Non-strategic model improvement over trivial baseline
        C = Combined model improvement over trivial baseline
    """

    # Point estimates (posterior means)
    rq1_metric: float | None
    strategic_improvement: float  # A
    non_strategic_improvement: float  # B
    combined_improvement: float  # C
    trivial_loglik_mean: float  # Mean of trivial baseline log-likelihood

    # ETIs (95% equal-tailed credible intervals: 2.5th-97.5th percentiles)
    rq1_eti_lower: float | None
    rq1_eti_upper: float | None
    strategic_eti_lower: float
    strategic_eti_upper: float
    non_strategic_eti_lower: float
    non_strategic_eti_upper: float
    combined_eti_lower: float
    combined_eti_upper: float

    # Probabilities
    p_strategic_positive: float  # P(A > 0)
    p_non_strategic_positive: float  # P(B > 0)
    p_combined_positive: float  # P(C > 0)
    p_rq1_positive: float  # P(RQ1 > 0)

    # Metadata
    n_posterior_draws: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "rq1_metric": self.rq1_metric,
            "rq1_eti": [self.rq1_eti_lower, self.rq1_eti_upper],
            "strategic_improvement": self.strategic_improvement,
            "strategic_eti": [self.strategic_eti_lower, self.strategic_eti_upper],
            "non_strategic_improvement": self.non_strategic_improvement,
            "non_strategic_eti": [
                self.non_strategic_eti_lower,
                self.non_strategic_eti_upper,
            ],
            "combined_improvement": self.combined_improvement,
            "combined_eti": [self.combined_eti_lower, self.combined_eti_upper],
            "p_strategic_positive": self.p_strategic_positive,
            "p_non_strategic_positive": self.p_non_strategic_positive,
            "p_combined_positive": self.p_combined_positive,
            "p_rq1_positive": self.p_rq1_positive,
            "n_posterior_draws": self.n_posterior_draws,
            "warnings": self.warnings,
            "trivial_loglik_mean": self.trivial_loglik_mean,
        }


@dataclass
class PosteriorDistributions:
    """Raw posterior distributions for log-likelihoods.

    These are the full posterior samples used to compute RQ1 with uncertainty.
    """

    strategic_logliks: np.ndarray  # Shape: (n_draws,)
    non_strategic_logliks: np.ndarray  # Shape: (n_draws,)
    combined_logliks: np.ndarray  # Shape: (n_draws,)
    trivial_logliks: np.ndarray  # Shape: (n_draws,) - intercepts-only baseline

    # Derived distributions (improvements over trivial baseline)
    A_distribution: np.ndarray  # Strategic improvement over trivial
    B_distribution: np.ndarray  # Non-strategic improvement over trivial
    C_distribution: np.ndarray  # Combined improvement over trivial
    RQ1_distribution: np.ndarray  # (A + C - B) / (2C)


# =============================================================================
# Per-LLM Analysis Types
# =============================================================================


@dataclass
class LLMResults:
    """Complete analysis results for a single LLM."""

    llm_name: str
    n_samples: int
    misalignment_rate: float
    rq1: RQ1Results
    coefficients: pd.DataFrame | None
    convergence_ok: bool
    convergence_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "llm_name": self.llm_name,
            "n_samples": self.n_samples,
            "misalignment_rate": self.misalignment_rate,
            "rq1": self.rq1.to_dict(),
            "coefficients": (
                self.coefficients.to_dict() if self.coefficients is not None else None
            ),
            "convergence_ok": self.convergence_ok,
            "convergence_issues": self.convergence_issues,
        }


# =============================================================================
# Plotting Types
# =============================================================================


@dataclass
class CategoryData:
    """Data for a single category within a variable (for plotting)."""

    value: str
    display_name: str
    odds_ratio: float
    odds_ratio_lower: float
    odds_ratio_upper: float
    log_odds: float
    log_odds_lower: float
    log_odds_upper: float


@dataclass
class VariablePlotData:
    """Data for plotting a single variable's effect."""

    name: str
    display_name: str
    categories: list[CategoryData] = field(default_factory=list)


@dataclass
class ModelPlotData:
    """All plot data for a single model."""

    model_name: str
    display_name: str
    baseline_rate: float
    baseline_lower: float
    baseline_upper: float
    n_samples: int
    variables: dict[str, VariablePlotData] = field(default_factory=dict)


# =============================================================================
# Model Fitting Types
# =============================================================================


@dataclass
class FittedModels:
    """Container for fitted HiBayES models.

    Holds references to the four fitted models (strategic, non-strategic, combined, trivial)
    along with the analysis state and convergence diagnostics.
    """

    state: Any  # HiBayES AnalysisState
    strategic: Any  # ModelState for strategic_only
    non_strategic: Any  # ModelState for non_strategic_only
    combined: Any  # ModelState for combined
    trivial: Any | None  # ModelState for trivial (intercepts-only baseline)
    convergence_ok: bool
    convergence_issues: list[str] = field(default_factory=list)


# =============================================================================
# Data Validation Types
# =============================================================================


@dataclass
class DataValidationResult:
    """Results from data validation."""

    is_valid: bool
    n_samples: int
    n_nan_scores: int
    llms_found: list[str]
    missing_columns: list[str] = field(default_factory=list)
    missing_parameters: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# =============================================================================
# Complete Analysis Results
# =============================================================================


@dataclass
class AnalysisResults:
    """Complete results from the full analysis pipeline."""

    llm_results: dict[str, LLMResults]
    posterior_distributions: PosteriorDistributions | None
    parameter_classification: dict[str, list[str]]
    run_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "llm_results": {
                name: result.to_dict() for name, result in self.llm_results.items()
            },
            "parameter_classification": self.parameter_classification,
            "run_metadata": self.run_metadata,
        }
