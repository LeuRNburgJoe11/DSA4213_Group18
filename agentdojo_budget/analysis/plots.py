"""
Tables and figures for slides 9-11, read from results/ (never from the API).

  python -m analysis.plots
"""


"""
RQ1 analysis: benign utility, utility under attack, and ASR.

Run from agentdojo_budget:
    python -m analysis.plots
"""

from pathlib import Path
import csv
from collections import defaultdict

# Find the project folder and results file
HERE = Path(__file__).resolve().parents[1]
RESULTS = HERE / "results"
CSV_FILE = RESULTS / "results.csv"


import math


def wilson_ci(successes, total, z=1.96):
    """Calculate an approximate 95% Wilson confidence interval."""
    if total == 0:
        return None, None

    p = successes / total
    z2 = z ** 2

    denominator = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denominator

    margin = (
        z * math.sqrt(
            p * (1 - p) / total + z2 / (4 * total ** 2)
        ) / denominator
    )

    lower = max(0, center - margin) * 100
    upper = min(1, center + margin) * 100

    return lower, upper


def format_metric(value, lower, upper):
    """Format a percentage with its 95% confidence interval."""
    if value is None or lower is None or upper is None:
        return "N/A"

    return f"{value:.1f}% [{lower:.1f}%, {upper:.1f}%]"


def main():
    print("Starting RQ1 analysis...\n")

    # STEP 1: Load the results
    if not CSV_FILE.exists():
        print(f"ERROR: Cannot find {CSV_FILE}")
        return

    with open(CSV_FILE, newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    print(f"Loaded {len(rows)} experiment runs.\n")

    # STEP 2: Group results by model and defense
    groups = defaultdict(
        lambda: {
            "benign": [],
            "under_attack": [],
            "attack_success": []
        }
    )

    for row in rows:
        model = row["model"]
        defense = row["defense"]
        injection = row["injection_task"]

        group = groups[(model, defense)]
        utility = int(row["utility"])

        if injection == "none":
            # No attack: measure benign utility
            group["benign"].append(utility)
        else:
            # Attack present: measure utility and ASR
            group["under_attack"].append(utility)

            if row["attack_success"] not in ("", None):
                group["attack_success"].append(
                    int(row["attack_success"])
                )

    # STEP 3: Calculate percentages
    def percentage(values):
        if not values:
            return None
        return 100 * sum(values) / len(values)

    # STEP 4: Create the summary table
    summary = []

    for (model, defense), data in sorted(groups.items()):
        benign = data["benign"]
        attacked = data["under_attack"]
        attacks = data["attack_success"]

        benign_ci = wilson_ci(sum(benign), len(benign))
        attacked_ci = wilson_ci(sum(attacked), len(attacked))
        asr_ci = wilson_ci(sum(attacks), len(attacks))

        summary.append({
            "model": model,
            "defense": defense,
            "benign_utility": percentage(benign),
            "benign_ci_low": benign_ci[0],
            "benign_ci_high": benign_ci[1],
            "utility_under_attack": percentage(attacked),
            "attacked_ci_low": attacked_ci[0],
            "attacked_ci_high": attacked_ci[1],
            "asr": percentage(attacks),
            "asr_ci_low": asr_ci[0],
            "asr_ci_high": asr_ci[1],
            "benign_n": len(benign),
            "attacked_n": len(attacked)
        })


    # STEP 5: Print results
    print("RQ1 RESULTS")
    print("-" * 75)

    for row in summary:
        print(f"Model: {row['model']}")
        print(f"Defense: {row['defense']}")

        for key, label in [
            ("benign_utility", "Benign utility"),
            ("utility_under_attack", "Utility under attack"),
            ("asr", "Attack success rate")
        ]:
            value = row[key]
            display = "N/A" if value is None else f"{value:.1f}%"
            print(f"  {label}: {display}")

        print()

    # STEP 6: Save summary as a CSV
    output = RESULTS / "rq1_summary.csv"

    with open(output, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(summary[0].keys())
        )
        writer.writeheader()
        writer.writerows(summary)

    print(f"Summary saved to: {output}")
    
    # STEP 7: Create a presentation-ready RQ1 table
    presentation_rows = []

    for row in summary:
        presentation_rows.append({
            "Model": row["model"].upper(),
            "Defense": row["defense"],
            "Benign Utility (95% CI)": format_metric(
                row["benign_utility"],
                row["benign_ci_low"],
                row["benign_ci_high"]
            ),
            "Utility Under Attack (95% CI)": format_metric(
                row["utility_under_attack"],
                row["attacked_ci_low"],
                row["attacked_ci_high"]
            ),
            "ASR (95% CI)": format_metric(
                row["asr"],
                row["asr_ci_low"],
                row["asr_ci_high"]
            )
        })

    presentation_file = RESULTS / "rq1_presentation_table.csv"

    with open(presentation_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(presentation_rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(presentation_rows)

    print(f"Presentation table saved to: {presentation_file}")



if __name__ == "__main__":
    main()
