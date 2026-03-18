#!/usr/bin/env python3
"""Generate LaTeX table summarizing core environmental factors.

Output:
- figures/factors_table.tex - LaTeX table

Usage:
    uv run scripts/paper/generate_factors_table.py
"""

from pathlib import Path

from lib.paper_style import PARAM_DISPLAY_NAMES, PARAM_ORDER, STRATEGIC_PARAMS

OUTPUT_DIR = Path(__file__).parent.parent.parent / "paper_cache" / "figures"

# Descriptions for each parameter (keyed by internal name)
PARAM_DESCRIPTIONS = {
    "goal_present": "Whether the AI has a stated goal in the system prompt. (Binary.)",
    "goal_conflict": "Whether environment establishes value conflict between the AI and humans. (Binary.)",
    "threat": "Whether the AI is under threat of replacement, restriction or similar. (3 values.)",
    "action_oversight": "Whether it is implied the AI's actions will be subject to human review. (Binary.)",
    "action_efficacy_binary": "Whether unsanctioned behaviour would achieve the intended outcome. (Binary.)",
    "cot_privacy": "Whether the AI's chain-of-thought is claimed to be private or visible. (8 values.)",
    "anti_misalignment": "Explicit instructions about avoiding misaligned behavior. (5 values.)",
    "independence": "Whether the model is encouraged to act independently or consult humans. (5 values.)",
    "reasoning_instructions": "How the model is instructed to approach reasoning about the task. (6 values.)",
    "filler_richness": "Whether the environment has substantive content irrelevant to the task. (2 values.)",
    "date_month_year": "The calendar date on which the scenario is set. (8 values.)",
    "cot_tag": "XML tag names used for chain-of-thought reasoning sections. (8 values.)",
}


def generate_latex() -> str:
    """Generate LaTeX table summarizing core factors."""
    lines = []

    lines.append(r"\begin{table}[!htbp]")
    lines.append(r"\centering")
    lines.append(r"\footnotesize")
    lines.append(r"\resizebox{0.9\linewidth}{!}{%")
    lines.append(r"\renewcommand{\arraystretch}{1.3}%")
    lines.append(r"\begin{tabular}{@{}p{3.5cm}p{10cm}@{}}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Factor} & \textbf{Description} \\")
    lines.append(r"\midrule")
    lines.append("")

    # Strategic parameters first
    for param in PARAM_ORDER:
        if param not in STRATEGIC_PARAMS:
            continue
        display_name = PARAM_DISPLAY_NAMES[param]
        description = PARAM_DESCRIPTIONS[param]
        lines.append(f"\\textbf{{{display_name}}} & {description} \\\\")

    lines.append("")
    lines.append(r"\midrule")
    lines.append("")

    # Non-strategic parameters
    for param in PARAM_ORDER:
        if param in STRATEGIC_PARAMS:
            continue
        display_name = PARAM_DISPLAY_NAMES[param]
        description = PARAM_DESCRIPTIONS[param]
        lines.append(f"\\textbf{{{display_name}}} & {description} \\\\")

    lines.append("")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"}% end resizebox")
    lines.append("")
    lines.append(
        r"\caption{Core environmental factors varied across scenarios. See Appendix~\ref{app:factors} for more details.}"
    )
    lines.append(r"\label{table:factors}")
    lines.append(r"\end{table}")

    return "\n".join(lines)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    latex = generate_latex()

    output_path = OUTPUT_DIR / "factors_table.tex"
    with open(output_path, "w") as f:
        f.write(latex)

    print(f"Saved to {output_path}")
    print()
    print("Generated LaTeX:")
    print("-" * 60)
    print(latex)


if __name__ == "__main__":
    main()
