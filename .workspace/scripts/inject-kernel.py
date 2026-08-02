#!/usr/bin/env python3
"""Inject the commit-discipline kernel into a tracked repo's CLAUDE.md.

    inject-kernel.py <name>...      inject into these repos
    inject-kernel.py --all          inject into every enabled repo
    inject-kernel.py --check        report drift; write nothing (exit 1 if any)

The kernel is what makes a child repo's git history readable as telemetry: it
holds the commit schema the status run parses. Without it, the summary degrades
to bare commit titles.

THREE THINGS THIS DELIBERATELY DOES NOT DO
  * It never commits. The workspace does not commit into child repos — you `cd`
    into the repo and commit there, so the change lands with your identity, your
    review, and that repo's hooks. Same rule the CLAUDE.md block states.
  * It never writes anything workspace-specific. The block is committed to a
    SHARED repo that several developers may each track from their own workspace;
    a name or version stamp in it would make two workspaces overwrite each
    other's block forever.
  * It carries no daily-plan rules. Plans moved up into each developer's
    workspace, so a plan file in a shared repo is a file two people overwrite.

Everything outside the markers is preserved verbatim, exactly like the
workspace's own CLAUDE.md block.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _status_lib import (  # noqa: E402
    StatusError, WORKSPACE_DIR, WORKSPACE_ROOT, enabled_repos, load_repos, repo_dir,
)

KERNEL = WORKSPACE_DIR / "templates" / "commit-kernel.md"
BEGIN = "<!-- git-workspace-commits:begin -->"
END = "<!-- git-workspace-commits:end -->"


def kernel_text():
    if not KERNEL.exists():
        raise StatusError(f"missing {KERNEL} — re-run the generator's update.sh")
    text = KERNEL.read_text()
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < 0:
        raise StatusError(f"{KERNEL} has no marker block")
    return text[i:j + len(END)]


def find_block(text, what):
    """(start, end) of the managed block, or None. Refuses anything malformed.

    A half-open or duplicated block means an edit could silently destroy the
    repo's own directives — worse than not updating at all.
    """
    nb, ne = text.count(BEGIN), text.count(END)
    if nb > 1 or ne > 1:
        raise StatusError(f"{what} has {nb} begin / {ne} end markers — expected at "
                          "most one block. Delete the extras and re-run.")
    i, j = text.find(BEGIN), text.find(END)
    if i >= 0 and j < 0:
        raise StatusError(f"{what} has a begin marker but no end marker.")
    if j >= 0 and i < 0:
        raise StatusError(f"{what} has an end marker but no begin marker.")
    if i >= 0 and j < i:
        raise StatusError(f"{what} has its end marker before its begin marker.")
    return (i, j + len(END)) if i >= 0 else None


def apply_kernel(claude_path, block, write=True):
    """Returns one of: created | refreshed | appended | current | (write=False) stale."""
    if not claude_path.exists():
        if write:
            claude_path.write_text(
                f"# CLAUDE.md — {claude_path.parent.name}\n\n{block}\n")
        return "created"

    cur = claude_path.read_text()
    span = find_block(cur, str(claude_path))
    if span:
        if cur[span[0]:span[1]] == block:
            return "current"
        new = cur[:span[0]] + block + cur[span[1]:]
        action = "refreshed"
    else:
        sep = "" if cur.endswith("\n\n") else ("\n" if cur.endswith("\n") else "\n\n")
        new = cur + sep + block + "\n"
        action = "appended"
    if write:
        claude_path.write_text(new)
    return action


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="repo names from repos.yml")
    ap.add_argument("--all", action="store_true", help="every enabled repo")
    ap.add_argument("--check", action="store_true",
                    help="report drift and write nothing; exit 1 if any repo is stale")
    args = ap.parse_args()

    if args.all or (args.check and not args.names):
        repos = enabled_repos()
    elif args.names:
        by_name = {r["name"]: r for r in load_repos()}
        missing = [n for n in args.names if n not in by_name]
        if missing:
            sys.exit(f"inject-kernel: not registered: {', '.join(missing)}")
        repos = [by_name[n] for n in args.names]
    else:
        ap.error("name a repo, or pass --all")

    block = kernel_text()
    stale, touched = [], []
    for r in repos:
        d = repo_dir(r)
        if d is None:
            print(f"[inject-kernel] {r['name']}: no checkout — skipped", file=sys.stderr)
            continue
        result = apply_kernel(Path(d) / "CLAUDE.md", block, write=not args.check)
        if result == "current":
            if not args.check:
                print(f"[inject-kernel] {r['name']}: already current")
            continue
        if args.check:
            stale.append((r["name"], result))
        else:
            touched.append((r["name"], d, result))
            print(f"[inject-kernel] {r['name']}: {result}")

    if args.check:
        if not stale:
            print("[inject-kernel] every tracked repo carries the current kernel")
            return 0
        print("[inject-kernel] kernel drift:", file=sys.stderr)
        for name, what in stale:
            state = {"created": "no CLAUDE.md", "appended": "no kernel block",
                     "refreshed": "kernel is out of date"}[what]
            print(f"  * {name}: {state}", file=sys.stderr)
        print("\nFix with: .workspace/scripts/inject-kernel.py --all", file=sys.stderr)
        return 1

    if touched:
        print("\nThe workspace does not commit into child repos. For each one:")
        for name, d, _ in touched:
            try:
                rel = Path(d).relative_to(WORKSPACE_ROOT)
            except ValueError:
                rel = d
            print(f"  cd {rel} && git add CLAUDE.md && git commit -m "
                  f"\"docs(claude): refresh the commit-discipline kernel\"")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except StatusError as e:
        sys.exit(f"inject-kernel: {e}")
