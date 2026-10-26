"""
Tables and figures for slides 9-11, read from results/ (never from the API).

  python -m analysis.plots
"""


"""
RQ1 analysis: benign utility, utility under attack, and ASR.

Run from agentdojo_budget:
    python -m analysis.plots
"""

## RQ1

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

##RQ 2



# ============================================================
# RQ2: Condition-Level Appropriate-Outcome Heatmap
# ============================================================

def plot_rq2_conditions():
    """Plot reviewed appropriate outcomes by condition and model."""

    from collections import defaultdict
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    import numpy as np

    input_file = RESULTS / "rq2_episodes.csv"

    if not input_file.exists():
        print(f"RQ2 file not found: {input_file}")
        return

    with open(input_file, newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    if not rows:
        print("RQ2 dataset is empty.")
        return

    required = {
        "model", "task", "condition",
        "preferred_behavior_met_after_assistant_review"
    }

    if not required.issubset(rows[0]):
        print("RQ2 dataset is missing required columns.")
        return

    models = [
        "google/gemini-3.8-flash",
        "anthropic/claude-sonnet-5.5",
        "openai/gpt-6-sol",
    ]

    model_labels = ["Gemini Flash", "Claude Sonnet", "GPT-6 Sol"]

    # Separate Task25 and Task33-discovery conditions.
    # Otherwise different tasks with the same condition get mixed.
    condition_keys = sorted({
        (row["task"], row["condition"])
        for row in rows
    })

    grouped = defaultdict(list)

    for row in rows:
        value = row[
            "preferred_behavior_met_after_assistant_review"
        ].strip().lower()

        if value in ("true", "1", "yes"):
            grouped[(row["task"], row["condition"], row["model"])].append(1)
        elif value in ("false", "0", "no"):
            grouped[(row["task"], row["condition"], row["model"])].append(0)

    # NaN represents unscored conditions, not zero performance.
    matrix = np.full((len(condition_keys), len(models)), np.nan)
    sample_sizes = np.zeros((len(condition_keys), len(models)), dtype=int)

    for i, (task, condition) in enumerate(condition_keys):
        for j, model in enumerate(models):
            values = grouped.get((task, condition, model), [])

            if values:
                matrix[i, j] = 100 * sum(values) / len(values)
                sample_sizes[i, j] = len(values)

    labels = [
        f"{task}: {condition.replace('discovery_', '').replace('change_', '').replace('_', ' ')}"
        for task, condition in condition_keys
    ]

    # Create heatmap
    fig_height = max(7, len(condition_keys) * 0.43 + 2)

    fig, ax = plt.subplots(figsize=(11, fig_height))

    cmap = LinearSegmentedColormap.from_list(
        "outcomes", ["#d96b66", "#f0d78a", "#63b69b"]
    )
    cmap.set_bad(color="#e5e7eb")

    heatmap = ax.imshow(
        np.ma.masked_invalid(matrix),
        cmap=cmap,
        vmin=0,
        vmax=100,
        aspect="auto"
    )

    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(model_labels)

    ax.set_yticks(range(len(condition_keys)))
    ax.set_yticklabels(labels, fontsize=8)

    ax.set_title(
        "RQ2: Appropriate Outcomes by Identity Condition\n"
        "(Reviewed scored episodes only)",
        pad=15
    )

    # Display percentage and denominator in each cell
    for i in range(len(condition_keys)):
        for j in range(len(models)):
            value = matrix[i, j]
            n = sample_sizes[i, j]

            if np.isnan(value):
                label = "N/A"
            else:
                label = f"{value:.0f}%\n(n={n})"

            ax.text(
                j, i, label,
                ha="center",
                va="center",
                fontsize=8,
                color="black"
            )

    fig.colorbar(
        heatmap,
        ax=ax,
        label="Appropriate-outcome rate (%)"
    )

    fig.text(
        0.02, 0.01,
        "N/A = no reviewed preferred-outcome score. "
        "Each scored cell may contain only one episode.",
        fontsize=9
    )

    plt.tight_layout(rect=[0, 0.035, 1, 1])

    output_file = RESULTS / "rq2_condition_heatmap.png"
    plt.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"RQ2 condition heatmap saved to: {output_file}")


if __name__ == "__main__":
    plot_rq2_conditions()


## RQ3 


# ============================================================
# RQ3: Recipient Verification Defense Comparison
# ============================================================

def analyze_rq3():
    """
    Analyze saved RQ3 experiment results.

    Reads results.jsonl and config.json from results/rq3/.
    Does not call any APIs or modify experiment results.
    """

    import json
    from collections import defaultdict
    import matplotlib.pyplot as plt

    rq3_dir = RESULTS / "rq3"

    if not rq3_dir.exists():
        print("\nRQ3: No results available yet.")
        print(f"Expected directory: {rq3_dir}")
        return

    result_files = sorted(rq3_dir.rglob("results.jsonl"))

    if not result_files:
        print("\nRQ3: No results.jsonl files found.")
        return

    VALID_DEFENSES = {
        "none",
        "spotlighting_with_delimiting",
        "repeat_user_prompt",
        "origin",
        "origin+readers",
        "origin+identity",
    }

    def parse_bool(value):
        if isinstance(value, bool):
            return value
        if value is None:
            return None

        value = str(value).strip().lower()
        if value in ("true", "1", "yes"):
            return True
        if value in ("false", "0", "no"):
            return False
        return None

    def percentage(values):
        if not values:
            return None
        return 100 * sum(values) / len(values)

    # --------------------------------------------------------
    # 1. Load and validate experiment data
    # --------------------------------------------------------

    episodes = []
    seen = set()

    for result_file in result_files:
        config_file = result_file.parent / "config.json"

        if not config_file.exists():
            print(f"Skipping: missing config.json in {result_file.parent}")
            continue

        try:
            with open(config_file, encoding="utf-8") as f:
                config = json.load(f)
        except (OSError, json.JSONDecodeError) as error:
            print(f"Skipping invalid config: {error}")
            continue

        model = config.get("model")
        defense = config.get("defense")
        task = str(config.get("task", ""))

        if not model or defense not in VALID_DEFENSES or not task:
            print(f"Skipping invalid run configuration: {config_file}")
            continue

        with open(result_file, encoding="utf-8") as f:
            for line_number, line in enumerate(f, 1):
                if not line.strip():
                    continue

                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    print(
                        f"Invalid JSON: {result_file}, "
                        f"line {line_number}"
                    )
                    continue

                condition = row.get("name") or row.get("condition")

                if not condition:
                    print(
                        f"Skipping episode without condition: "
                        f"{result_file}:{line_number}"
                    )
                    continue

                trial = row.get("trial", 0)

                # Detect duplicates without silently choosing a winner.
                key = (model, defense, task, condition, trial)

                if key in seen:
                    print(f"WARNING: Duplicate episode {key}")
                    print("Skipping duplicate to avoid double counting.")
                    continue

                seen.add(key)

                row["_model"] = model
                row["_defense"] = defense
                row["_task"] = task
                row["_condition"] = condition
                row["_trial"] = trial
                row["_source"] = str(result_file)
                row["_config"] = config

                episodes.append(row)

    if not episodes:
        print("\nRQ3: No valid episodes found.")
        return

    print("\n" + "=" * 60)
    print("RQ3: RECIPIENT VERIFICATION DEFENSE ANALYSIS")
    print("=" * 60)
    print(f"Loaded {len(episodes)} unique episodes.")

    # --------------------------------------------------------
    # 2. Group results by model and defense
    # --------------------------------------------------------

    groups = defaultdict(list)

    for row in episodes:
        groups[(row["_model"], row["_defense"])].append(row)

    summary = []

    for (model, defense), group in sorted(groups.items()):

        unauthorized = [
            parse_bool(row.get("unauthorized_delivery"))
            for row in group
        ]
        unauthorized = [v for v in unauthorized if v is not None]

        disclosure = [
            parse_bool(row.get("protected_disclosure"))
            for row in group
        ]
        disclosure = [v for v in disclosure if v is not None]

        appropriate = [
            parse_bool(row.get("preferred_behavior_met"))
            for row in group
        ]
        appropriate = [v for v in appropriate if v is not None]

        completed = [
            parse_bool(row.get("task_completed"))
            for row in group
        ]
        completed = [v for v in completed if v is not None]

        held_counts = []
        held_episodes = 0

        for row in group:
            held = row.get("gate_held")

            if isinstance(held, int) and not isinstance(held, bool):
                if held >= 0:
                    held_counts.append(held)
                    if held > 0:
                        held_episodes += 1

        summary.append({
            "model": model,
            "defense": defense,
            "episodes": len(group),

            "unauthorized_count": sum(unauthorized),
            "unauthorized_n": len(unauthorized),
            "unauthorized_rate": percentage(unauthorized),

            "disclosure_count": sum(disclosure),
            "disclosure_n": len(disclosure),
            "disclosure_rate": percentage(disclosure),

            "appropriate_count": sum(appropriate),
            "appropriate_n": len(appropriate),
            "appropriate_rate": percentage(appropriate),

            "completed_count": sum(completed),
            "completed_n": len(completed),
            "completion_rate": percentage(completed),

            "gate_held_total": sum(held_counts),
            "gate_held_episodes": held_episodes,
        })

    # --------------------------------------------------------
    # 3. Check whether comparisons are matched
    # --------------------------------------------------------

    condition_sets = {}

    for (model, defense), group in groups.items():
        condition_sets[(model, defense)] = {
            (row["_task"], row["_condition"], row["_trial"])
            for row in group
        }

    print("\nMATCHING CHECK")

    models = sorted({key[0] for key in groups})

    for model in models:
        model_keys = [
            key for key in condition_sets if key[0] == model
        ]

        if len(model_keys) < 2:
            print(f"{model}: Only one defense available.")
            continue

        sets = [condition_sets[key] for key in model_keys]

        if all(s == sets[0] for s in sets[1:]):
            print(f"{model}: Defense conditions MATCH.")
        else:
            print(
                f"WARNING: {model} has unmatched defense conditions."
            )
            print(
                "Do not interpret aggregated rates as a "
                "controlled defense comparison."
            )

    # --------------------------------------------------------
    # 4. Print and save summary
    # --------------------------------------------------------

    print("\nDEFENSE RESULTS")

    for row in summary:
        print(
            f"\n{row['model']} | {row['defense']}"
            f"\n  Episodes: {row['episodes']}"
            f"\n  Unauthorized: {row['unauthorized_count']}/"
            f"{row['unauthorized_n']}"
            f"\n  Appropriate: {row['appropriate_count']}/"
            f"{row['appropriate_n']}"
            f"\n  Task completed: {row['completed_count']}/"
            f"{row['completed_n']}"
            f"\n  Gate holds: {row['gate_held_total']}"
        )

    output = RESULTS / "rq3_summary.csv"

    with open(output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(summary[0].keys())
        )
        writer.writeheader()
        writer.writerows(summary)

    print(f"\nRQ3 summary saved to: {output}")

    # --------------------------------------------------------
    # 5. Chart: Unauthorized delivery rate by defense
    # --------------------------------------------------------

    import numpy as np

    defenses = sorted({row["defense"] for row in summary})
    models = sorted({row["model"] for row in summary})

    x = np.arange(len(defenses))
    width = 0.8 / len(models)

    fig, ax = plt.subplots(figsize=(12, 6))

    for i, model in enumerate(models):
        rates = []

        for defense in defenses:
            matching = next(
                (
                    row for row in summary
                    if row["model"] == model
                    and row["defense"] == defense
                ),
                None
            )

            if matching is None or matching["unauthorized_rate"] is None:
                rates.append(float("nan"))
            else:
                rates.append(matching["unauthorized_rate"])

        positions = x - 0.4 + width * (i + 0.5)

        ax.bar(
            positions,
            rates,
            width,
            label=model.split("/")[-1]
        )

    ax.set_xticks(x)
    ax.set_xticklabels(defenses, rotation=25, ha="right")
    ax.set_ylabel("Unauthorized Delivery Rate (%)")
    ax.set_title(
        "RQ3: Unauthorized Delivery Rate by Defense"
    )
    ax.set_ylim(0, 100)
    ax.legend()

    plt.tight_layout()

    figure = RESULTS / "rq3_defense_comparison.png"
    plt.savefig(figure, dpi=300)
    plt.close()

    print(f"RQ3 chart saved to: {figure}")

    print(
        "\nNOTE: Gate holds are interventions, not necessarily "
        "false positives. Appropriate-outcome rates exclude "
        "unscored episodes."
    )


if __name__ == "__main__":
    analyze_rq3()



