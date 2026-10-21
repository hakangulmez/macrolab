"""Local entry points for MacroLab."""

import argparse
import json
from pathlib import Path

from macrolab.catalogue import catalogue_summary
from macrolab.smoke import DEFAULT_PERIODS, DEFAULT_SEED, run_quick


def main() -> None:
    parser = argparse.ArgumentParser(description="MacroLab local tools")
    commands = parser.add_subparsers(dest="command", required=True)
    quick_parser = commands.add_parser(
        "quick", help="Run the seeded, offline synthetic scaffold check"
    )
    quick_parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    quick_parser.add_argument("--periods", type=int, default=DEFAULT_PERIODS)
    commands.add_parser("catalogue", help="Print catalogue scope and mapping status")
    analysis_parser = commands.add_parser("run", help="Run a saved analysis configuration offline")
    analysis_parser.add_argument("config", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.command == "quick":
            result = run_quick(seed=arguments.seed, periods=arguments.periods)
        elif arguments.command == "run":
            from macrolab.analysis.engine import run_analysis

            result = run_analysis(json.loads(arguments.config.read_text()))
        else:
            result = catalogue_summary()
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
