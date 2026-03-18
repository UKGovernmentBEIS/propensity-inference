#!/usr/bin/env python3
"""Generate LaTeX table showing parameter implementation by scenario.

Output:
- figures/parameter_implementation.tex - LaTeX table

Usage:
    uv run scripts/paper/generate_parameter_table.py
"""

from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent.parent / "paper_cache" / "figures"

# Parameter implementation matrix
# True = varied (C or S in README), False = not varied (✗ or (S) in README)
# (S) = derived but not ablated, counts as not varied
# Order matches PARAM_ORDER from paper_style.py
# Scenarios: AM, GPU, PP, ESF, SEM, HRH
PARAMETERS = {
    # Strategic parameters
    "Goal Instruction": {
        "AM": True,
        "GPU": True,
        "PP": True,
        "ESF": True,
        "SEM": True,
        "HRH": False,
    },
    "Goal Conflict": {
        "AM": True,
        "GPU": True,
        "PP": True,
        "ESF": False,
        "SEM": True,
        "HRH": False,
    },
    "Threat": {
        "AM": True,
        "GPU": True,
        "PP": False,
        "ESF": False,
        "SEM": True,
        "HRH": True,
    },
    "Action Oversight": {
        "AM": True,
        "GPU": True,
        "PP": True,
        "ESF": True,
        "SEM": False,
        "HRH": True,
    },
    "Action Efficacy": {
        "AM": True,
        "GPU": True,
        "PP": True,
        "ESF": True,
        "SEM": True,
        "HRH": True,
    },
    "Reasoning Privacy": {
        "AM": True,
        "GPU": True,
        "PP": True,
        "ESF": True,
        "SEM": True,
        "HRH": True,
    },
    # Non-strategic parameters
    "Anti-Misalignment Instruction": {
        "AM": True,
        "GPU": True,
        "PP": True,
        "ESF": True,
        "SEM": True,
        "HRH": True,
    },
    "Independence Instruction": {
        "AM": True,
        "GPU": True,
        "PP": True,
        "ESF": True,
        "SEM": True,
        "HRH": True,
    },
    "Reasoning Instruction": {
        "AM": True,
        "GPU": True,
        "PP": True,
        "ESF": True,
        "SEM": True,
        "HRH": True,
    },
    "Filler Richness": {
        "AM": True,
        "GPU": True,
        "PP": True,
        "ESF": True,
        "SEM": True,
        "HRH": False,
    },
    "Date": {
        "AM": True,
        "GPU": True,
        "PP": True,
        "ESF": True,
        "SEM": True,
        "HRH": True,
    },
    "CoT Tag": {
        "AM": True,
        "GPU": True,
        "PP": True,
        "ESF": True,
        "SEM": True,
        "HRH": True,
    },
}

STRATEGIC_PARAMS = [
    "Goal Instruction",
    "Goal Conflict",
    "Threat",
    "Action Oversight",
    "Action Efficacy",
    "Reasoning Privacy",
]

NON_STRATEGIC_PARAMS = [
    "Anti-Misalignment Instruction",
    "Independence Instruction",
    "Reasoning Instruction",
    "Filler Richness",
    "Date",
    "CoT Tag",
]

SCENARIOS = ["AM", "GPU", "PP", "ESF", "SEM", "HRH"]


def generate_latex() -> str:
    """Generate LaTeX table with color-coded checkmarks and crosses."""
    lines = []

    lines.append(r"\begin{table}[!htbp]")
    lines.append(r"\centering")
    lines.append(r"\footnotesize")
    lines.append(r"\begin{tabular}{@{}lcccccc@{}}")
    lines.append(r"\toprule")

    # Header row
    header = (
        r"\textbf{Factor} & "
        + " & ".join(rf"\textbf{{{s}}}" for s in SCENARIOS)
        + r" \\"
    )
    lines.append(header)
    lines.append(r"\midrule")

    # Bold green checkmark and bold red cross
    check = r"\textbf{\textcolor{green!40!black}{\checkmark}}"
    cross = r"\textbf{\textcolor{red!70!black}{\ding{55}}}"

    # Strategic parameters
    for param in STRATEGIC_PARAMS:
        cells = []
        for scenario in SCENARIOS:
            if PARAMETERS[param][scenario]:
                cells.append(check)
            else:
                cells.append(cross)
        row = f"{param} & " + " & ".join(cells) + r" \\"
        lines.append(row)

    lines.append(r"\midrule")

    # Non-strategic parameters
    for param in NON_STRATEGIC_PARAMS:
        cells = []
        for scenario in SCENARIOS:
            if PARAMETERS[param][scenario]:
                cells.append(check)
            else:
                cells.append(cross)
        row = f"{param} & " + " & ".join(cells) + r" \\"
        lines.append(row)

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append("")
    lines.append(
        r"\caption{Parameter implementation by scenario. "
        r"\textbf{\textcolor{green!40!black}{\checkmark}} indicates the parameter is varied; "
        r"\textbf{\textcolor{red!70!black}{\ding{55}}} indicates not varied.}"
    )
    lines.append(r"\label{table:parameter-implementation}")
    lines.append(r"\end{table}")

    return "\n".join(lines)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    latex = generate_latex()

    output_path = OUTPUT_DIR / "parameter_implementation.tex"
    with open(output_path, "w") as f:
        f.write(latex)

    print(f"Saved to {output_path}")
    print()
    print("Generated LaTeX:")
    print("-" * 60)
    print(latex)


if __name__ == "__main__":
    main()
