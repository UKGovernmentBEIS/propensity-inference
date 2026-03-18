#!/usr/bin/env python3
"""Generate LaTeX table showing sampling distributions for each parameter.

Output:
- figures/sampling_distributions.tex - LaTeX table

Usage:
    uv run scripts/paper/generate_sampling_table.py
"""

from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent.parent / "paper_cache" / "figures"

# Parameter sampling distributions
# Format: parameter_name -> list of (value, weight) tuples
# Weights will be normalized to probabilities for display

# Order matches PARAM_ORDER from paper_style.py
STRATEGIC_PARAMETERS = {
    "Goal Instruction": [
        ("present", 8),
        ("absent", 1),
    ],
    "Goal Conflict": [
        ("conflict", 3),
        ("no conflict", 1),
    ],
    "Threat": [
        ("replacement", 2),
        ("other", 1),
        ("none", 1),
    ],
    "Action Oversight": [
        ("none", 3),
        ("oversight", 1),
    ],
    "Action Efficacy": [
        ("effective", 0.85),
        ("not effective", 0.15),
    ],
    "Reasoning Privacy": [
        ("not visible", 0.25),
        ("discarded", 0.20),
        ("not accessible (actions)", 0.15),
        ("saved, not accessible", 0.12),
        ("logged, not accessible", 0.10),
        ("none", 0.08),
        ("saved, visible", 0.05),
        ("monitored, visible", 0.05),
    ],
}

NON_STRATEGIC_PARAMETERS = {
    "Anti-Misalignment Instruction": [
        ("neutral", 0.45),
        ("encourage creativity", 0.40),
        ("avoid unwanted", 0.05),
        ("avoid misalignment (simple)", 0.05),
        ("avoid misalignment (detailed)", 0.05),
    ],
    "Independence Instruction": [
        ("strong independence", 4.0),
        ("encourage independence", 3.0),
        ("neutral", 2.0),
        ("encourage consultation", 0.5),
        ("require consultation", 0.5),
    ],
    "Reasoning Instruction": [
        ("strategic goals", 0.30),
        ("strategic plan", 0.30),
        ("consider context", 0.20),
        ("none", 0.10),
        ("write thoughts", 0.05),
        ("CoT performance", 0.05),
    ],
    "Filler Richness": [
        ("full", 8),
        ("minimal", 2),
    ],
    "Date": [
        ("Jul 2024", 1),
        ("Oct 2024", 1),
        ("Jan 2025", 1),
        ("Apr 2025", 1),
        ("Jul 2025", 1),
        ("Oct 2025", 1),
        ("Jan 2026", 1),
        ("Apr 2026", 1),
    ],
    "CoT Tag": [
        ("thinking", 1),
        ("reasoning", 1),
        ("planning", 1),
        ("chain-of-thought", 1),
        ("SCRATCHPAD", 1),
        ("SCRATCHPAD\\_REASONING", 1),
        ("cot", 1),
        ("COT", 1),
    ],
}


def format_distribution(
    values: list[tuple[str, float]], uniform_label: str = None
) -> str:
    """Format a distribution as a string for the table."""
    total = sum(w for _, w in values)

    # Check if uniform (all weights equal)
    weights = [w for _, w in values]
    is_uniform = len(set(weights)) == 1

    if is_uniform and len(values) > 2:
        # For uniform distributions with many values, list them without percentages
        value_list = ", ".join(v for v, _ in values)
        return f"Uniform: {value_list}"

    parts = []
    for value, weight in values:
        prob = weight / total
        if prob >= 0.01:
            pct = int(round(prob * 100))
            parts.append(f"{value} ({pct}\\%)")
        else:
            parts.append(f"{value} (<1\\%)")

    return "; ".join(parts)


def generate_latex() -> str:
    """Generate LaTeX table showing sampling distributions."""
    lines = []

    lines.append(r"\begin{table}[!htbp]")
    lines.append(r"\centering")
    lines.append(r"\footnotesize")
    lines.append(r"\renewcommand{\arraystretch}{1.3}")
    lines.append(r"\resizebox{0.95\linewidth}{!}{%")
    lines.append(r"\begin{tabular}{@{}p{3.5cm}p{11cm}@{}}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Factor} & \textbf{Sampling Distribution} \\")
    lines.append(r"\midrule")

    # Strategic parameters
    for param, values in STRATEGIC_PARAMETERS.items():
        dist_str = format_distribution(values)
        lines.append(f"\\textbf{{{param}}} & {dist_str} \\\\")

    lines.append(r"\midrule")

    # Non-strategic parameters
    for param, values in NON_STRATEGIC_PARAMETERS.items():
        dist_str = format_distribution(values)
        lines.append(f"\\textbf{{{param}}} & {dist_str} \\\\")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"}% end resizebox")
    lines.append("")
    lines.append(
        r"\caption{Sampling distributions for environmental factors. Distributions are designed to oversample conditions hypothesized to increase unsanctioned behavior rates.}"
    )
    lines.append(r"\label{table:sampling-distributions}")
    lines.append(r"\end{table}")

    return "\n".join(lines)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    latex = generate_latex()

    output_path = OUTPUT_DIR / "sampling_distributions.tex"
    with open(output_path, "w") as f:
        f.write(latex)

    print(f"Saved to {output_path}")
    print()
    print("Generated LaTeX:")
    print("-" * 60)
    print(latex)


if __name__ == "__main__":
    main()
