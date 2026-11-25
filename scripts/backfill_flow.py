"""Seed data/cohort.json's flow log from snapshots in git history (the sweep does this
automatically when the log is missing). Usage: python scripts/backfill_flow.py"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.backfill import seed_flow_log  # noqa: E402


def main() -> int:
    path = ROOT / "data" / "cohort.json"
    cohort = json.loads(path.read_text())
    out = seed_flow_log(ROOT, cohort, int(time.time() * 1000))
    if not out:
        print("No stored snapshots found.")
        return 1
    live = [r for r in (cohort.get("flow_log") or []) if r["t"] > out[-1]["t"]]
    cohort["flow_log"] = sorted(out + live, key=lambda r: r["t"])
    path.write_text(json.dumps(cohort, separators=(",", ":")))
    print(f"Wrote {len(cohort['flow_log'])} flow rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
