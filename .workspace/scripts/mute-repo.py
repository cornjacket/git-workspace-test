#!/usr/bin/env python3
"""Quiet a repo in the status rollup, without unregistering it.

    mute-repo.py <name>            keep tracking, hide it on quiet days
    mute-repo.py <name> --skip     skip it entirely — no summary, no plan row
    mute-repo.py <name> --unmute   undo either of the above

Two flavors, because "stop nagging me about this" and "stop tracking this" are
different wishes:

  report_inactivity: false   still summarised when you commit there; just never
                             appears in the "No updates" list on a quiet day.
                             The right setting for a finished-but-live repo.
  enabled: false             dropped from the run entirely — no telemetry, no
                             plan row. The right setting for something parked.

Neither removes the repo. That is `delete-repo`.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _repos_edit as R  # noqa: E402
from _status_lib import REPOS_YML  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--skip", action="store_true",
                   help="set enabled: false — skip the repo entirely")
    g.add_argument("--unmute", action="store_true",
                   help="restore enabled: true and report_inactivity: true")
    args = ap.parse_args()

    if not REPOS_YML.exists():
        sys.exit("mute-repo: no .workspace/repos.yml")
    text = REPOS_YML.read_text()
    if args.name not in R.names(text):
        known = ", ".join(R.names(text)) or "(none)"
        sys.exit(f"mute-repo: no repo named '{args.name}'. Registered: {known}")

    if args.unmute:
        text = R.set_field(text, args.name, "enabled", "true")
        text = R.set_field(text, args.name, "report_inactivity", "true")
        msg = f"'{args.name}' is fully reported again"
    elif args.skip:
        text = R.set_field(text, args.name, "enabled", "false")
        msg = f"'{args.name}' is skipped entirely (enabled: false)"
    else:
        text = R.set_field(text, args.name, "report_inactivity", "false")
        msg = (f"'{args.name}' stays tracked but is hidden on quiet days "
               "(report_inactivity: false)")

    R.validate(text)
    REPOS_YML.write_text(text)
    print(f"[mute-repo] {msg}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except R.RepoEditError as e:
        sys.exit(f"mute-repo: {e}")
