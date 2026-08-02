#!/usr/bin/env python3
"""Register a repo in this workspace and clone it.

    add-repo.py <url> [--name N] [--path P] [--branch B] [--priority N]
                      [--tags a,b] [--no-clone]

This is the write path for `.workspace/repos.yml`: you never hand-edit that
file, you run this and the entry is maintained as a side effect. `bootstrap.sh`
is the replay path — it turns the resulting manifest back into checkouts on a
new machine.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _repos_edit as R  # noqa: E402
from _status_lib import REPOS_YML, WORKSPACE_DIR, WORKSPACE_ROOT, git  # noqa: E402


def name_from_url(url):
    """The repo name a `git clone` would pick: the last path segment, no .git."""
    tail = re.split(r"[/:]", url.rstrip("/"))[-1]
    return tail[:-4] if tail.endswith(".git") else tail


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", help="clone URL (ssh or https)")
    ap.add_argument("--name", help="short identifier (default: derived from the URL)")
    ap.add_argument("--path", help="checkout path relative to the workspace root "
                                   "(default: the name)")
    ap.add_argument("--branch", default="main", help="branch to check out (default: main)")
    ap.add_argument("--priority", type=int, help="band, 1 = highest (default: unset -> 3)")
    ap.add_argument("--tags", help="comma-separated labels, e.g. app,generator")
    ap.add_argument("--no-clone", action="store_true",
                    help="register only; leave the checkout to `make bootstrap`")
    args = ap.parse_args()

    name = args.name or name_from_url(args.url)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        sys.exit(f"add-repo: '{name}' is not a usable repo name — "
                 "pass --name with letters, digits, '.', '_', '-'.")
    path = (args.path or name).strip("/")

    text = REPOS_YML.read_text() if REPOS_YML.exists() else "repos: []\n"
    if name in R.names(text):
        sys.exit(f"add-repo: '{name}' is already registered. "
                 f"Use delete-repo first, or pass --name to register it under another name.")
    for existing in R.validate(text):
        if existing.get("path") == path:
            sys.exit(f"add-repo: path '{path}' is already used by "
                     f"'{existing['name']}' — pass --path to place this one elsewhere.")

    dest = WORKSPACE_ROOT / path
    if dest.exists() and not (dest / ".git").exists():
        sys.exit(f"add-repo: {dest} already exists and is not a git checkout. "
                 "Move it aside or pass --path.")

    # Clone BEFORE writing the entry: a bad URL or a network failure should
    # leave repos.yml untouched rather than registering a repo that does not
    # exist. (Re-running after a failure is then a clean retry.)
    if not args.no_clone and not (dest / ".git").exists():
        print(f"[add-repo] cloning {args.url} -> {path}")
        r = git(["clone", "--branch", args.branch, args.url, str(dest)], check=False)
        if r.returncode != 0:
            sys.exit(f"add-repo: clone failed, repos.yml not modified.\n{r.stderr.strip()}")
    elif (dest / ".git").exists():
        print(f"[add-repo] {path} is already checked out — registering it as is")

    entry = R.render_entry([
        ("name", name),
        ("url", args.url),
        ("path", path),
        ("type", "standard"),
        ("branch", args.branch),
        ("priority", args.priority),
        ("tags", f"[{', '.join(t.strip() for t in args.tags.split(','))}]" if args.tags else None),
    ])
    new_text = R.append_entry(text, entry)
    R.validate(new_text)
    REPOS_YML.write_text(new_text)
    print(f"[add-repo] registered '{name}' in .workspace/repos.yml")

    # Seed a plan slot so the repo shows up in daily-plan-summary.md immediately
    # — as "no plan" rather than not at all, which is the useful nudge.
    plan_dir = WORKSPACE_DIR / "plans" / name
    plan = plan_dir / "daily-plan.md"
    if not plan.exists():
        plan_dir.mkdir(parents=True, exist_ok=True)
        from datetime import date
        plan.write_text(
            f"# Daily plan — {date.today().isoformat()}\n\n"
            f"_Your plan for {name}. Per-developer: it lives in your workspace, not in\n"
            f"the shared repo, so two developers never collide over one plan file._\n\n"
            "## Focus / plan\n\n- _What are you doing in this repo next?_\n"
        )
        print(f"[add-repo] seeded .workspace/plans/{name}/daily-plan.md")

    # The commit kernel is what makes this repo's git log readable as telemetry,
    # so it goes in at registration rather than waiting to be remembered.
    kernel_note = ""
    if (dest / ".git").exists():
        import subprocess
        r = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "inject-kernel.py"), name],
            capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        if r.returncode != 0:
            sys.stderr.write(r.stderr)
        elif "already current" not in r.stdout:
            kernel_note = (f"  * Commit the kernel inside the child: cd {path} && "
                           "git add CLAUDE.md && git commit")

    print()
    print("Next:")
    print(f"  * Add '{name}' to the remote routine's `sources` pre-clone list, or the")
    print("    scheduled run cannot read its git log (the sandbox has no checkouts).")
    if kernel_note:
        print(kernel_note)
    print("  * Commit the workspace: repos.yml and the new plan slot are tracked.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except R.RepoEditError as e:
        sys.exit(f"add-repo: {e}")
