"""Run the reviewed deterministic research-assistant reference set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from invest_engine.research import evaluate_reference_set  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=ROOT / "research/reference_set.yaml", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate_reference_set(args.path), indent=2))


if __name__ == "__main__":
    main()
