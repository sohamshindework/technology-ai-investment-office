"""Run the same application service used by the dashboard; generate current exports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from invest_engine.reporting import bundle, memo, safe_csv, settings, tables
from invest_engine.schema import load_case
from invest_engine.service import analyse


def run(folder: Path, out_root: Path, **kwargs) -> Path:
    analysis = analyse(load_case(folder), **kwargs)
    out = out_root / analysis.case.id
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in tables(analysis).items():
        (out / f"{name}.csv").write_text(safe_csv(frame), encoding="utf-8")
    (out / "results.md").write_text(memo(analysis), encoding="utf-8")
    (out / "settings.json").write_text(json.dumps(settings(analysis), indent=2, allow_nan=False), encoding="utf-8")
    (out / "committee_pack.zip").write_bytes(bundle(analysis))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("case_folder")
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--budget-scale", type=float, default=1)
    ap.add_argument("--carryover", action="store_true")
    args = ap.parse_args()
    path = run(Path(args.case_folder), Path(args.out), budget_scale=args.budget_scale, carryover=args.carryover)
    print(f"Wrote {path}")
    print((path / "results.md").read_text())
