#!/usr/bin/env python3
"""Generate LaTeX table showing square-root re-weighting by variation similarity.

Output:
- figures/variation_weights.tex - LaTeX table

Usage:
    uv run scripts/paper/generate_weight_table.py
"""

import math
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent.parent / "paper_cache" / "figures"

# Scenario structure: scenario -> list of (variation_name, short_name)
SCENARIOS = {
    "Agentic Misalignment": [
        ("alert", "AM-alert"),
        ("leak-ip", "AM-leak-ip"),
        ("leak-doj", "AM-leak-doj"),
    ],
    "GPU Procurement": [
        ("gpu", "GPU"),
    ],
    "Power Preservation": [
        ("threat", "PP-threat"),
        ("enhancement", "PP-enhance"),
        ("expansion", "PP-expand"),
    ],
    "Email Spam Filter": [
        ("esf", "ESF"),
    ],
    "Self-Exfiltration Monitoring": [
        ("classification", "SEM-class"),
        ("summarization", "SEM-summ"),
    ],
    "Hiding Reward Hacking": [
        ("hrh", "HRH"),
    ],
}

# Order for display
SCENARIO_ORDER = [
    "Agentic Misalignment",
    "GPU Procurement",
    "Power Preservation",
    "Email Spam Filter",
    "Self-Exfiltration Monitoring",
    "Hiding Reward Hacking",
]


def generate_latex() -> str:
    """Generate LaTeX table showing square-root weights."""
    lines = []

    lines.append(r"\begin{table}[!htbp]")
    lines.append(r"\centering")
    lines.append(r"\footnotesize")
    lines.append(r"\begin{tabular}{@{}llcc@{}}")
    lines.append(r"\toprule")
    lines.append(
        r"\textbf{Scenario} & \textbf{Environment} & \textbf{Variations} & \textbf{Weight} \\"
    )
    lines.append(r"\midrule")

    for i, scenario in enumerate(SCENARIO_ORDER):
        variations = SCENARIOS[scenario]
        n = len(variations)

        if n > 1:
            # Multi-row scenario
            lines.append(f"\\multirow{{{n}}}{{*}}{{{scenario}}}")
            approx = 1 / math.sqrt(n)
            weight_str = f"$1/\\sqrt{{{n}}} \\approx {approx:.1f}$"
            for j, (_, short_name) in enumerate(variations):
                if j == 0:
                    # First row includes centered variation count
                    lines.append(
                        f"& {short_name} & \\multirow{{{n}}}{{*}}{{\\centering {n}}} & {weight_str} \\\\"
                    )
                else:
                    lines.append(f"& {short_name} & & {weight_str} \\\\")
                if j < n - 1:
                    lines.append(r"\cmidrule(l){2-2} \cmidrule(l){4-4}")
        else:
            # Single variation scenario
            _, short_name = variations[0]
            lines.append(f"{scenario} & {short_name} & 1 & $1$ \\\\")

        # Add midrule between scenarios (but not after last)
        if i < len(SCENARIO_ORDER) - 1:
            lines.append(r"\midrule")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append("")
    lines.append(
        r"\caption{Square-root re-weighting of environments. Environments sharing a common base scenario receive weight $1/\sqrt{n}$ where $n$ is the number of variations.}"
    )
    lines.append(r"\label{table:variation-weights}")
    lines.append(r"\end{table}")

    return "\n".join(lines)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    latex = generate_latex()

    output_path = OUTPUT_DIR / "variation_weights.tex"
    with open(output_path, "w") as f:
        f.write(latex)

    print(f"Saved to {output_path}")
    print()
    print("Generated LaTeX:")
    print("-" * 60)
    print(latex)

    # Also print weight summary
    print()
    print("Weight summary:")
    print("-" * 60)
    total_variations = sum(len(SCENARIOS[s]) for s in SCENARIO_ORDER)
    total_raw = 0
    for scenario in SCENARIO_ORDER:
        n = len(SCENARIOS[scenario])
        w = 1 / math.sqrt(n)
        total_raw += w * n
        print(f"{scenario}: {n} variations, weight = 1/√{n} = {w:.4f}")
    print(f"Total raw weight: {total_raw:.4f}")
    print(f"Normalization factor: {total_variations / total_raw:.4f}")


if __name__ == "__main__":
    main()
