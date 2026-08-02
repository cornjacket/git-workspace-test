"""Shared helpers for the workspace status subsystem.

Ported from project-status's tools/_lib.py, with three structural changes that
come from the work living *inside* a workspace instead of in a standalone
tracker repo:

  * **No `tracked/` cache locally.** The child repos are already checked out
    beside the workspace at the paths `repos.yml` declares, so the local run
    reads them in place. The remote routine still has no checkouts of its own,
    so it falls back to the platform's pre-cloned sources.
  * **Plans moved up into the workspace.** A plan is *per-developer* intent, so
    it lives at `.workspace/plans/<repo>/daily-plan.md` — in this developer's own
    workspace — not in the shared child repo where two developers would collide.
  * **Author-scoped telemetry.** Every git-log read filters `--author`, so each
    developer's rollup shows only their own commits. Required, not optional: the
    remote sandbox has no ambient git identity to fall back on.
"""
import json
import os
import subprocess
from datetime import date as _date
from pathlib import Path

import yaml

# .workspace/scripts/_status_lib.py -> .workspace -> the workspace root.
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = WORKSPACE_DIR.parent

REPOS_YML = WORKSPACE_DIR / "repos.yml"
CONFIG_YML = WORKSPACE_DIR / "config.yml"
STATE_DIR = WORKSPACE_DIR / "state"
STATE_JSON = STATE_DIR / "state.json"
ARCHIVE_DIR = STATE_DIR / "archive"
PLANS_DIR = WORKSPACE_DIR / "plans"
PROMPTS_DIR = WORKSPACE_DIR / "prompts"

# Top-level deliverables — the daily dashboard.
SUMMARY_MD = WORKSPACE_ROOT / "summary.md"
DAILY_PLAN_SUMMARY_MD = WORKSPACE_ROOT / "daily-plan-summary.md"

# The workspace's own plan slot. Aggregated FIRST: inter-repo work outranks any
# single repo's, and it is the tier that otherwise has nowhere to be seen.
WORKSPACE_PLAN_KEY = "_workspace"

# In a Claude remote routine the platform pre-clones every declared `source` at
# /home/user/<name> through an authenticated proxy. Direct clones from inside
# that sandbox hit a TLS-inspecting proxy and 401 even for public repos, so the
# pre-cloned trees MUST be reused.
PREBUILT_SOURCE_ROOT = Path("/home/user")

# Well-known SHA-1 of git's empty tree — the baseline range on a first run.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

DEFAULT_PRIORITY = 3

# The placeholder setup.sh writes when it cannot resolve an author. Reaching a
# status run with this still in place means the summary would be scoped to
# nobody, so the run refuses rather than emitting a silently-empty rollup.
AUTHOR_PLACEHOLDER = "CHANGEME@example.invalid"


class StatusError(RuntimeError):
    """A misconfiguration the operator must fix — reported, never worked around."""


# ---------------------------------------------------------------------------
# Config and membership
# ---------------------------------------------------------------------------
def load_config():
    if not CONFIG_YML.exists():
        raise StatusError(f"missing {CONFIG_YML} — is this a git-workspace?")
    with open(CONFIG_YML) as f:
        return yaml.safe_load(f) or {}


def workspace_name():
    return (load_config().get("name") or WORKSPACE_ROOT.name).strip()


def git_authors():
    """The emails the summary is scoped to. Hard-fails on an unresolved author.

    A wrong or empty author does not fail loudly on its own — it silently
    produces an empty rollup that looks like "you did nothing today". That is
    the failure mode worth refusing outright.
    """
    raw = load_config().get("git_author")
    authors = [raw] if isinstance(raw, str) else list(raw or [])
    authors = [str(a).strip() for a in authors if str(a).strip()]
    if not authors:
        raise StatusError(
            f"no git_author in {CONFIG_YML}. The summary is author-scoped, so "
            "the workspace must name whose commits to report."
        )
    if any(a == AUTHOR_PLACEHOLDER for a in authors):
        raise StatusError(
            f"git_author in {CONFIG_YML} is still the placeholder "
            f"'{AUTHOR_PLACEHOLDER}'. Replace it with your git email — otherwise "
            "the rollup would be scoped to nobody and silently come back empty."
        )
    return authors


def load_repos():
    """Normalized repo dicts from .workspace/repos.yml, in file order.

    The membership schema (name/url/path/type/branch/parent_repo_path) is the
    workspace's; the status flags (enabled/priority/report_inactivity) are
    project-status's, folded in here.
    """
    if not REPOS_YML.exists():
        return []
    with open(REPOS_YML) as f:
        data = yaml.safe_load(f) or {}
    out = []
    for r in data.get("repos") or []:
        name = r.get("name")
        if not name:
            continue
        out.append({
            "name": name,
            "url": r.get("url", ""),
            "path": r.get("path", name),
            "type": r.get("type", "standard"),
            "branch": r.get("branch", "main"),
            "enabled": r.get("enabled", True),
            "report_inactivity": r.get("report_inactivity", True),
            # Band, not a rank: ties are expected and fall back to repos.yml
            # order. Lower = more important; unset sorts last rather than
            # silently claiming the top band.
            "priority": int(r.get("priority", DEFAULT_PRIORITY)),
        })
    return out


def enabled_repos():
    return [r for r in load_repos() if r["enabled"]]


def prebuilt_source_path(name):
    """The platform's pre-cloned checkout for `name`, or None (remote only)."""
    if not os.environ.get("CLAUDE_CODE_REMOTE"):
        return None
    p = PREBUILT_SOURCE_ROOT / name
    return p if (p / ".git").exists() else None


def repo_dir(repo):
    """Where this repo's git history actually is, or None if unavailable.

    Locally that is the checkout sitting beside the workspace — no `tracked/`
    cache, because the working copies are right there. Remotely it is the
    pre-cloned source.
    """
    prebuilt = prebuilt_source_path(repo["name"])
    if prebuilt:
        return prebuilt
    d = WORKSPACE_ROOT / repo["path"]
    # Worktree-safe: a linked worktree's .git is a FILE, not a directory.
    return d if (d / ".git").exists() else None


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
def load_state():
    if not STATE_JSON.exists():
        return {}
    with open(STATE_JSON) as f:
        return json.load(f)


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_JSON, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------
def git(args, cwd=None, check=True):
    return subprocess.run(
        ["git"] + args,
        cwd=str(cwd) if cwd else None,
        check=check,
        capture_output=True,
        text=True,
    )


def author_args(authors):
    """`--author` flags. git ORs repeated --author, which is what we want for a
    developer who commits under more than one email."""
    return [f"--author={a}" for a in authors]


def head_commit(d):
    return git(["rev-parse", "HEAD"], cwd=d, check=False).stdout.strip()


# ASCII control chars as git-log delimiters. Commit bodies are multi-line, so
# "%s%n%b" is unparseable across records; these never occur in real text.
_RECORD_SEP = "\x1e"
_UNIT_SEP = "\x1f"


def _parse_message(raw):
    """Split a raw commit message into (title, context, impact, body).

    Parsing the raw message ourselves rather than leaning on git's %s/%b is
    deliberate: git treats the whole first paragraph as the subject, so a commit
    written WITHOUT a blank line after the title would swallow [Context]/[Impact]
    into %s and leave %b empty.
    """
    lines = raw.splitlines()
    title = ""
    rest_start = 0
    for i, ln in enumerate(lines):
        if ln.strip():
            title = ln.strip()
            rest_start = i + 1
            break
    context_lines, impact_lines = [], []
    current = None
    for raw_line in lines[rest_start:]:
        line = raw_line.strip()
        low = line.lower()
        if low.startswith("- [context]:"):
            current = context_lines
            current.append(line.split(":", 1)[1].strip())
        elif low.startswith("- [impact]:"):
            current = impact_lines
            current.append(line.split(":", 1)[1].strip())
        elif not line:
            current = None
        elif current is not None:
            current.append(line)
    return (
        title,
        " ".join(p for p in context_lines if p).strip(),
        " ".join(p for p in impact_lines if p).strip(),
        raw.strip("\n"),
    )


def git_telemetry(d, rev_range, authors):
    """Author-scoped commit telemetry for `rev_range`, newest first.

    Reads the structured commit schema each tracked repo is held to:
        <domain>(<scope>): <high-level functional summary>
        - [Context]: why this was done / what was learned
        - [Impact]: how it alters the project or system behavior
    """
    fmt = f"{_RECORD_SEP}%h{_UNIT_SEP}%B"
    out = git(["log", f"--pretty=format:{fmt}", *author_args(authors), rev_range],
              cwd=d, check=False).stdout
    commits = []
    for record in out.split(_RECORD_SEP):
        if not record.strip():
            continue
        parts = record.split(_UNIT_SEP, 1)
        title, context, impact, body = _parse_message(parts[1] if len(parts) > 1 else "")
        commits.append({
            "hash": parts[0].strip(),
            "title": title,
            "context": context,
            "impact": impact,
            "body": body,
        })
    return commits


def author_file_stat(d, rev_range, authors):
    """Per-file +/- totals across the author's commits in `rev_range`.

    `git diff --stat <range>` cannot be author-filtered — it would report every
    developer's changes — so the numbers are summed from `git log --numstat`
    over the author's commits only.
    """
    out = git(["log", "--numstat", "--pretty=format:", *author_args(authors), rev_range],
              cwd=d, check=False).stdout
    files = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, removed, path = parts
        if added == "-" or removed == "-":       # binary file
            continue
        a, r = files.get(path, (0, 0))
        files[path] = (a + int(added), r + int(removed))
    if not files:
        return ""
    rows = sorted(files.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))
    width = max(len(p) for p, _ in rows)
    lines = [f" {p.ljust(width)} | {a + r:>4} +{a} -{r}" for p, (a, r) in rows]
    total_a = sum(a for _, (a, _) in rows)
    total_r = sum(r for _, (_, r) in rows)
    n = len(rows)
    lines.append(f" {n} file{'' if n == 1 else 's'} changed, "
                 f"{total_a} insertion{'' if total_a == 1 else 's'}(+), "
                 f"{total_r} deletion{'' if total_r == 1 else 's'}(-)")
    return "\n".join(lines)


def days_between(iso_a, iso_b):
    return (_date.fromisoformat(iso_b) - _date.fromisoformat(iso_a)).days


def format_telemetry(commits):
    """Render git_telemetry() output for a human or an LLM prompt."""
    if not commits:
        return "(none)"
    blocks = []
    for c in commits:
        lines = [f"- {c['hash']} {c['title']}"]
        if c["context"]:
            lines.append(f"    [Context]: {c['context']}")
        if c["impact"]:
            lines.append(f"    [Impact]: {c['impact']}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------
def gather_report(today=None, since=None, authors=None):
    """One dict per enabled repo, in repos.yml order.

    status ∈ {ACTIVE, INACTIVE, INACTIVE_SUPPRESSED, UNAVAILABLE}

    ACTIVE means "this developer committed here in the window" — not "the repo
    moved". A repo advanced entirely by a teammate has nothing to say in *your*
    author-scoped rollup, so it reads as INACTIVE for you while state.json still
    tracks the real HEAD, keeping the window correct for the next run.

    The window is the durable `last_commit..HEAD` from state.json, which
    preserves catch-up after a missed day. `since` (e.g. "24 hours ago") is an
    ad-hoc override that ignores state entirely.
    """
    today = today or _date.today().isoformat()
    authors = authors or git_authors()
    state = load_state()
    out = []
    for r in enabled_repos():
        name = r["name"]
        s = state.get(name, {})
        last = s.get("last_commit") or EMPTY_TREE
        last_act = s.get("last_activity_date")
        entry = {
            "name": name,
            "path": r["path"],
            "url": r["url"],
            "priority": r["priority"],
            "status": None,
            "last_commit": last,
            "head": None,
            "last_activity_date": last_act,
            "days_inactive": days_between(last_act, today) if last_act else None,
            "commit_telemetry": None,
            "file_stat": None,
            "commit_list": None,
            "report_inactivity": r["report_inactivity"],
        }
        d = repo_dir(r)
        if d is None:
            entry["status"] = "UNAVAILABLE"
            out.append(entry)
            continue
        entry["head"] = head_commit(d)
        if since:
            base = git(["rev-list", "-1", f"--before={since}", "HEAD"],
                       cwd=d, check=False).stdout.strip() or EMPTY_TREE
            rev_range = f"{base}..HEAD"
        else:
            rev_range = f"{last}..HEAD"
        telemetry = git_telemetry(d, rev_range, authors)
        if not telemetry:
            entry["status"] = "INACTIVE" if r["report_inactivity"] else "INACTIVE_SUPPRESSED"
        else:
            entry["status"] = "ACTIVE"
            entry["commit_telemetry"] = telemetry
            entry["file_stat"] = author_file_stat(d, rev_range, authors)
            entry["commit_list"] = git(
                ["log", "--oneline", *author_args(authors), rev_range], cwd=d, check=False
            ).stdout
        out.append(entry)
    return out


def advance_state(today=None):
    """Move each repo's window forward to its current HEAD.

    HEAD is stored unfiltered even though the report is author-scoped: the
    window must not re-offer a teammate's commits tomorrow just because they
    were not yours today.
    """
    today = today or _date.today().isoformat()
    state = load_state()
    for r in enabled_repos():
        d = repo_dir(r)
        if d is None:
            continue
        head = head_commit(d)
        prev = state.get(r["name"], {})
        moved = prev.get("last_commit") != head
        state[r["name"]] = {
            "last_commit": head,
            "last_synced": today,
            "last_activity_date": today if moved else prev.get("last_activity_date"),
        }
    save_state(state)
    return state
