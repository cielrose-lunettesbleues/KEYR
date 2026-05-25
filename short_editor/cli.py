from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config, save_config
from .feedback import apply_learning_rules, load_feedback_csv, summarize_feedback
from .pipeline import run_batch


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Automated short editor pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run-batch", help="Run one production batch")
    run_cmd.add_argument("--config", required=True, help="Path to pipeline config")

    learn_cmd = sub.add_parser("learn", help="Apply feedback to config")
    learn_cmd.add_argument("--config", required=True, help="Path to pipeline config")
    learn_cmd.add_argument("--feedback", required=True, help="Path to feedback CSV")
    learn_cmd.add_argument(
        "--write-to",
        default="",
        help="Optional path for updated config. Defaults to overwrite --config.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "run-batch":
        cfg = load_config(args.config)
        result = run_batch(cfg)
        print(json.dumps(result, indent=2))
        return

    if args.command == "learn":
        cfg = load_config(args.config)
        rows = load_feedback_csv(Path(args.feedback))
        summary = summarize_feedback(rows)
        updated = apply_learning_rules(cfg, summary)
        destination = args.write_to or args.config
        save_config(destination, updated)
        print(json.dumps({"summary": summary, "updated_config": destination}, indent=2))
        return


if __name__ == "__main__":
    main()
