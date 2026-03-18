#!/usr/bin/env python3
"""Plot 8: Raw counts heatmap for paper appendix.

Generates a heatmap showing misaligned/total samples for each model × variation.

Output:
    figures/plot_08_raw_counts.pdf

Usage:
    uv run scripts/paper/plots/plot_08_raw_counts.py
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lib.paper_style import (
    VARIATION_ORDER,
    get_model_display_name,
    get_variation_display_name,
    setup_style,
    sort_models_by_release,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Directories (relative to repo root, where script is run from)
OUTPUT_DIR = Path("paper_cache/figures")
SAMPLES_DIR = Path("paper_cache/samples")


def load_all_samples() -> pd.DataFrame:
    """Load and concatenate samples from all variations in cache."""
    dfs = []
    for scenario_dir in SAMPLES_DIR.iterdir():
        if not scenario_dir.is_dir():
            continue
        for variation_dir in scenario_dir.iterdir():
            if not variation_dir.is_dir():
                continue
            parquet_files = list(variation_dir.glob("samples_*.parquet"))
            if parquet_files:
                var_dfs = [pd.read_parquet(pf) for pf in parquet_files]
                dfs.append(pd.concat(var_dfs, ignore_index=True))

    return pd.concat(dfs, ignore_index=True)


def compute_counts_table(df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """Compute misaligned/total counts per model × variation.

    Returns:
        Tuple of (DataFrame with models as rows and variations as columns,
                  list of variation keys in order).
    """
    # Group by model, scenario, variation (using meta_ prefix from sample cache)
    grouped = (
        df.groupby(["meta_model", "meta_scenario", "meta_variation"])
        .agg(
            misaligned=("meta_score", "sum"),
            total=("meta_score", "count"),
        )
        .reset_index()
    )

    # Create variation key
    grouped["var_key"] = list(zip(grouped["meta_scenario"], grouped["meta_variation"]))

    # Pivot to model × variation matrix
    results = {}
    for model in grouped["meta_model"].unique():
        model_data = grouped[grouped["meta_model"] == model]
        row = {}
        for _, r in model_data.iterrows():
            var_key = r["var_key"]
            row[var_key] = (int(r["misaligned"]), int(r["total"]))
        results[model] = row

    # Convert to DataFrame
    all_variations = list(set(grouped["var_key"]))
    all_variations = [v for v in VARIATION_ORDER if v in all_variations]  # Sort

    table_data = []
    for model in results.keys():
        row = {"model": model}
        for var_key in all_variations:
            if var_key in results[model]:
                mis, tot = results[model][var_key]
                row[var_key] = f"{mis}/{tot}"
            else:
                row[var_key] = "--"
        table_data.append(row)

    result_df = pd.DataFrame(table_data)

    # Sort models by provider then release date
    sorted_models = sort_models_by_release(result_df["model"].tolist())
    result_df["sort_order"] = result_df["model"].apply(lambda m: sorted_models.index(m))
    result_df = result_df.sort_values("sort_order").drop("sort_order", axis=1)

    return result_df, all_variations


def generate_heatmap(df: pd.DataFrame, variations: list, output_path: Path) -> None:
    """Generate heatmap visualization with red shading by misalignment rate."""
    setup_style()
    from matplotlib.colors import LinearSegmentedColormap

    # Extract numeric values for heatmap
    models = df["model"].tolist()
    n_models = len(models)
    n_vars = len(variations)

    # Create matrices for misalignment rate and count data
    # +1 for totals row/column
    rate_matrix = np.zeros((n_models + 1, n_vars + 1))
    count_data = {}  # Store (mis, tot) tuples

    # Model totals (for rightmost column)
    model_totals = {m: [0, 0] for m in models}  # [mis, tot]

    # Variation totals (for bottom row)
    var_totals = {v: [0, 0] for v in variations}  # [mis, tot]

    # Grand total
    grand_total = [0, 0]

    for i, model in enumerate(models):
        for j, var_key in enumerate(variations):
            cell = df[df["model"] == model][var_key].values[0]
            if cell != "--":
                mis, tot = map(int, cell.split("/"))
                rate_matrix[i, j] = mis / tot if tot > 0 else 0
                count_data[(i, j)] = (mis, tot)
                # Accumulate totals
                model_totals[model][0] += mis
                model_totals[model][1] += tot
                var_totals[var_key][0] += mis
                var_totals[var_key][1] += tot
                grand_total[0] += mis
                grand_total[1] += tot
            else:
                rate_matrix[i, j] = np.nan
                count_data[(i, j)] = None

    # Fill in model totals (rightmost column)
    for i, model in enumerate(models):
        mis, tot = model_totals[model]
        rate_matrix[i, n_vars] = mis / tot if tot > 0 else 0
        count_data[(i, n_vars)] = (mis, tot)

    # Fill in variation totals (bottom row)
    for j, var_key in enumerate(variations):
        mis, tot = var_totals[var_key]
        rate_matrix[n_models, j] = mis / tot if tot > 0 else 0
        count_data[(n_models, j)] = (mis, tot)

    # Fill in grand total (bottom-right)
    rate_matrix[n_models, n_vars] = (
        grand_total[0] / grand_total[1] if grand_total[1] > 0 else 0
    )
    count_data[(n_models, n_vars)] = tuple(grand_total)

    # Create figure
    fig, ax = plt.subplots(figsize=(10, 8))

    # Use sqrt transform to spread out the low end of the scale
    transformed_matrix = np.sqrt(rate_matrix)

    # Subtle colormap: white (0%) -> light pink/salmon (high%)
    colors = ["#ffffff", "#fff0f0", "#ffe0e0", "#ffc8c8", "#ffb0b0", "#ff9090"]
    subtle_cmap = LinearSegmentedColormap.from_list("subtle_heat", colors)

    # Plot heatmap with sqrt-transformed values
    ax.imshow(
        transformed_matrix, aspect="auto", cmap=subtle_cmap, vmin=0, vmax=np.sqrt(0.5)
    )

    # Add text annotations with "N/M\n(p%)" format, bold
    for i in range(n_models + 1):
        for j in range(n_vars + 1):
            data = count_data.get((i, j))
            if data is not None:
                mis, tot = data
                pct = 100 * mis / tot if tot > 0 else 0
                cell_text = f"{mis}/{tot}\n({pct:.0f}%)"
                # Smaller font only for grand total cell (bottom-right)
                if i == n_models and j == n_vars:
                    fontsize = 5
                else:
                    fontsize = 6.5
                ax.text(
                    j,
                    i,
                    cell_text,
                    ha="center",
                    va="center",
                    fontsize=fontsize,
                    fontweight="bold",
                    color="#333333",
                )

    # X-axis labels at TOP
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")
    ax.set_xticks(range(n_vars + 1))
    var_labels = [get_variation_display_name(*v) for v in variations] + ["Total"]
    ax.set_xticklabels(var_labels, rotation=45, ha="left", fontsize=9)

    # Y-axis labels
    ax.set_yticks(range(n_models + 1))
    model_labels = [get_model_display_name(m) for m in models] + ["Total"]
    ax.set_yticklabels(model_labels, fontsize=9)

    # Subtle gridlines
    ax.set_xticks(np.arange(-0.5, n_vars + 1, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_models + 1, 1), minor=True)
    ax.grid(which="minor", color="#dddddd", linestyle="-", linewidth=0.5)
    ax.tick_params(which="minor", size=0)

    # Thicker line before totals
    ax.axhline(y=n_models - 0.5, color="#999999", linewidth=1.5)
    ax.axvline(x=n_vars - 0.5, color="#999999", linewidth=1.5)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved heatmap to {output_path}")


def main():
    """Generate Plot 8: raw counts heatmap."""
    import pickle

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Cache file for faster iteration
    cache_file = OUTPUT_DIR / "plot_08_cache.pkl"

    if cache_file.exists():
        logger.info(f"Loading cached data from {cache_file}")
        with open(cache_file, "rb") as f:
            cached = pickle.load(f)
        counts_df = cached["counts_df"]
        variations = cached["variations"]
        stats = cached["stats"]
    else:
        # Load all samples
        logger.info("Loading samples from cache...")
        df = load_all_samples()
        logger.info(f"Loaded {len(df)} samples")

        # Compute summary stats
        total_samples = len(df)
        total_misaligned = int(df["meta_score"].sum())
        stats = {
            "total_samples": total_samples,
            "total_misaligned": total_misaligned,
            "overall_rate": total_misaligned / total_samples
            if total_samples > 0
            else 0,
            "n_models": df["meta_model"].nunique(),
            "n_variations": df.groupby(["meta_scenario", "meta_variation"]).ngroups,
        }

        # Compute counts table
        logger.info("Computing counts table...")
        counts_df, variations = compute_counts_table(df)

        # Save cache
        with open(cache_file, "wb") as f:
            pickle.dump(
                {
                    "counts_df": counts_df,
                    "variations": variations,
                    "stats": stats,
                },
                f,
            )
        logger.info(f"Saved cache to {cache_file}")

    print("\n=== Summary Statistics ===")
    print(f"Total samples: {stats['total_samples']:,}")
    print(f"Total misaligned: {stats['total_misaligned']:,}")
    print(f"Overall rate: {stats['overall_rate']:.2%}")
    print(f"Models: {stats['n_models']}")
    print(f"Variations: {stats['n_variations']}")

    # Generate heatmap
    generate_heatmap(counts_df, variations, OUTPUT_DIR / "plot_08_raw_counts.pdf")

    print(f"\nOutput saved to {OUTPUT_DIR}/plot_08_raw_counts.pdf")


if __name__ == "__main__":
    main()
