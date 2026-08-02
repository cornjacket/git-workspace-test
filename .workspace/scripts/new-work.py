#!/usr/bin/env python3
"""Print the per-repo report of new work in this developer's commit window.

The human-readable form of _status_lib.gather_report(). run.py consumes the same
structured data directly, so what you read here is exactly what the summariser
is given — no second code path to drift.
"""
import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _status_lib import (  # noqa: E402
    StatusError, format_telemetry, gather_report, git_authors,
)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", "--window", dest="since", metavar="WHEN",
                    help="ad-hoc window override (e.g. '24 hours ago'); default "
                         "uses the durable last_commit..HEAD range from state.json")
    args = ap.parse_args()

    today = date.today().isoformat()
    authors = git_authors()
    report = gather_report(today=today, since=args.since, authors=authors)

    print(f"# Update report — {today}")
    print(f"_Scoped to: {', '.join(authors)}_\n")
    if not report:
        print("_(no enabled repos in .workspace/repos.yml)_")
        return 0

    for e in report:
        print(f"## {e['name']}")
        if e["status"] == "UNAVAILABLE":
            print("UNAVAILABLE — no readable checkout; run `make bootstrap` "
                  "(or add it to the remote routine's sources)\n")
            continue
        if e["status"] == "INACTIVE_SUPPRESSED":
            print("INACTIVE_SUPPRESSED — omitted from summary.md\n")
            continue
        if e["status"] == "INACTIVE":
            if e["last_activity_date"]:
                print(f"INACTIVE — no commits by you for {e['days_inactive']} days "
                      f"(last activity {e['last_activity_date']})\n")
            else:
                print("INACTIVE — no commits by you recorded yet\n")
            continue
        print(f"ACTIVE — {e['last_commit'][:8]}..{e['head'][:8]}\n")
        print("### commit telemetry")
        print(format_telemetry(e["commit_telemetry"]))
        print("\n### file stat")
        print(e["file_stat"] or "(none)")
        print("\n### commits")
        print(e["commit_list"] or "(none)")
        print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except StatusError as e:
        print(f"[new-work] {e}", file=sys.stderr)
        sys.exit(2)
