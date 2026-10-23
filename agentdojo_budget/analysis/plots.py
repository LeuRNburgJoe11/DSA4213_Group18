"""
Tables and figures for slides 9-11, read from results/ (never from the API).

  python -m analysis.plots
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
RESULTS = HERE / "results"


def main() -> None:
    raise NotImplementedError  # TODO: RQ1 ASR/utility table, RQ2 outcome bars, RQ3 gate comparison


if __name__ == "__main__":
    main()
