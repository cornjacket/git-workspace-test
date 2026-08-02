#!/usr/bin/env python3
"""The daily status run — one entry point for the whole cycle.

  1. sync        — report which repos are readable (local: they already are)
  2. gather      — classify each repo against YOUR commit window
  3. per repo    — `claude -p` summarises each ACTIVE repo's telemetry
  4. inactive    — deterministic one-liners, no LLM
  5. polish      — with >=2 ACTIVE repos, `claude -p` merges cross-repo themes
  6. summary.md  — prepend today's section
  7. aggregate   — rebuild daily-plan-summary.md (always, even with no commits)
  8. advance     — move state.json's window forward

The LLM steps (3 and 5) are skipped by `--dry-run`, which emits deterministic
placeholders instead — that is what makes the pipeline testable offline.

This writes files and stops. It never commits: on the remote side daily.sh owns
the branch-and-push, and locally the diff is the review surface.
"""
import argparse
import functools
import os
import subprocess
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _status_lib import (  # noqa: E402
    PROMPTS_DIR, SUMMARY_MD, StatusError, advance_state, format_telemetry,
    gather_report, git_authors, workspace_name,
)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
INSERT_MARKER = "<!-- new sections inserted below -->"

# The step scripts run as subprocesses and write straight to the terminal, so
# this process's own progress lines must not sit in a pipe buffer — otherwise
# the log reads out of order (aggregate's output appearing before "[run] ...").
print = functools.partial(print, flush=True)  # noqa: A001


def claude_p(prompt):
    """Invoke `claude -p`, piping the prompt on stdin (safer for large inputs)."""
    r = subprocess.run(["claude", "-p"], input=prompt, check=True,
                       capture_output=True, text=True)
    return r.stdout.strip()


def format_slice(e):
    return (
        f"Range: {e['last_commit'][:8]}..{e['head'][:8]}\n\n"
        f"## commit telemetry\n{format_telemetry(e['commit_telemetry'])}\n\n"
        f"## file stat\n{e['file_stat'] or '(none)'}\n\n"
        f"## commits\n{e['commit_list'] or '(none)'}\n"
    )


def render_per_repo(e, dry_run):
    if dry_run:
        return (f"### {e['name']}\n- (dry-run placeholder for "
                f"{e['last_commit'][:8]}..{e['head'][:8]}, "
                f"{len(e['commit_telemetry'])} commit(s))")
    template = (PROMPTS_DIR / "per-repo.md").read_text()
    return claude_p(template
                    .replace("{{REPO_NAME}}", e["name"])
                    .replace("{{REPO_SLICE}}", format_slice(e)))


def render_inactive_bullet(e):
    if e["last_activity_date"]:
        return f"- {e['name']} (for {e['days_inactive']} days)"
    return f"- {e['name']} (no activity recorded yet)"


def render_inactives_block(entries):
    if not entries:
        return ""
    return "### No updates\n" + "\n".join(render_inactive_bullet(e) for e in entries)


def polish(today, drafts_text, dry_run):
    if dry_run:
        return f"## {today}\n\n{drafts_text}"
    template = (PROMPTS_DIR / "polish.md").read_text()
    return claude_p(template
                    .replace("{{TODAY}}", today)
                    .replace("{{WORKSPACE_NAME}}", workspace_name())
                    .replace("{{DRAFTS}}", drafts_text))


def prepend_to_summary(section):
    """Newest day first. Creates summary.md if the routine has never run."""
    block = section.rstrip() + "\n"
    if not SUMMARY_MD.exists():
        SUMMARY_MD.write_text(
            f"# Summary — {workspace_name()}\n\n"
            "<!-- Author-scoped retrospective rollup, newest first. Written by "
            ".workspace/scripts/run.py. -->\n\n"
            f"{INSERT_MARKER}\n\n{block}"
        )
        return
    text = SUMMARY_MD.read_text()
    if INSERT_MARKER in text:
        new = text.replace(INSERT_MARKER, INSERT_MARKER + "\n\n" + block, 1)
    else:
        idx = text.find("\n## ")
        new = (text.rstrip() + "\n\n" + block) if idx == -1 \
            else text[:idx + 1] + block + "\n" + text[idx + 1:]
    SUMMARY_MD.write_text(new)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="skip `claude -p`; emit deterministic placeholders")
    ap.add_argument("--skip-sync", action="store_true")
    ap.add_argument("--skip-plans", action="store_true",
                    help="skip the aggregate-plans step")
    ap.add_argument("--skip-state", action="store_true",
                    help="do not advance state.json (re-runnable window)")
    ap.add_argument("--since", "--window", dest="since", metavar="WHEN",
                    help="ad-hoc window override (e.g. '24 hours ago')")
    args = ap.parse_args()

    # Resolve the author FIRST: everything downstream is scoped to it, and a
    # placeholder would produce a plausible-looking but empty rollup.
    authors = git_authors()
    print(f"[run] workspace '{workspace_name()}' — scoped to {', '.join(authors)}")

    if not args.skip_sync:
        subprocess.run([sys.executable, os.path.join(SCRIPTS_DIR, "sync.py")], check=True)

    today = date.today().isoformat()
    report = gather_report(today=today, since=args.since, authors=authors)

    drafts, inactive_entries, active_count = [], [], 0
    for e in report:
        if e["status"] == "INACTIVE_SUPPRESSED":
            continue
        if e["status"] == "UNAVAILABLE":
            print(f"[run] WARNING: {e['name']} has no readable checkout; skipping",
                  file=sys.stderr)
            continue
        if e["status"] == "INACTIVE":
            inactive_entries.append(e)
            continue
        print(f"[run] summarizing {e['name']}...")
        drafts.append(render_per_repo(e, args.dry_run))
        active_count += 1

    inactives = render_inactives_block(inactive_entries)
    if inactives:
        drafts.append(inactives)

    if drafts:
        drafts_text = "\n\n".join(drafts)
        if active_count >= 2:
            print("[run] polishing cross-repo section...")
            section = polish(today, drafts_text, args.dry_run)
        else:
            section = f"## {today}\n\n{drafts_text}"
        prepend_to_summary(section)
        print(f"[run] prepended the {today} section to summary.md")
    else:
        print("[run] nothing to report; summary.md untouched")

    # Plans aggregate even on a zero-commit day — the forward-looking half is
    # the point of the dashboard, and it is independent of git activity.
    if not args.skip_plans:
        subprocess.run([sys.executable, os.path.join(SCRIPTS_DIR, "aggregate-plans.py")],
                       check=True)

    if not args.skip_state:
        advance_state(today=today)
        print("[run] advanced state.json")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except StatusError as e:
        print(f"[run] {e}", file=sys.stderr)
        sys.exit(2)
