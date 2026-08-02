#!/usr/bin/env python3
"""Make every enabled repo's git history readable by the status run.

Locally this is almost a no-op: the child repos are already checked out beside
the workspace, so there is nothing to clone — the old `tracked/` cache existed
only because project-status was a standalone repo with no checkouts of its own.
It reports what is present and what is missing, and stops.

Remotely (inside a Claude routine sandbox) the checkouts do not exist. The
platform pre-clones every declared `source` at /home/user/<name>, which
_status_lib.repo_dir() picks up automatically, so this reports which repos the
routine can and cannot see. A repo missing there means it was never added to the
routine's `sources` list — the run cannot fetch it, and says so.

Read-only: it never clones, pulls, or modifies a child repo. Materializing a
missing checkout is bootstrap.sh's job, driven by repos.yml.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _status_lib import (  # noqa: E402
    StatusError, WORKSPACE_ROOT, enabled_repos, prebuilt_source_path, repo_dir,
)


def main():
    repos = enabled_repos()
    if not repos:
        print("[sync] no enabled repos in .workspace/repos.yml")
        return 0

    remote = bool(os.environ.get("CLAUDE_CODE_REMOTE"))
    print(f"[sync] {'remote routine' if remote else 'local'} — {len(repos)} enabled repo(s)")

    missing = []
    for r in repos:
        d = repo_dir(r)
        if d is None:
            missing.append(r)
            print(f"[sync] MISSING  {r['name']}")
            continue
        where = "pre-cloned" if prebuilt_source_path(r["name"]) else "local checkout"
        try:
            rel = d.relative_to(WORKSPACE_ROOT)
        except ValueError:
            rel = d
        print(f"[sync] ok       {r['name']}  ({where}: {rel})")

    if missing:
        names = ", ".join(r["name"] for r in missing)
        print(f"\n[sync] {len(missing)} repo(s) unreadable: {names}", file=sys.stderr)
        if remote:
            print("[sync] add them to the routine's `sources` pre-clone list — the "
                  "sandbox cannot clone them itself.", file=sys.stderr)
        else:
            print("[sync] run `make bootstrap` to materialize them.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except StatusError as e:
        print(f"[sync] {e}", file=sys.stderr)
        sys.exit(2)
