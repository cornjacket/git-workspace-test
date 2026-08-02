#!/usr/bin/env bash
# daily.sh — the entry point for the scheduled REMOTE status routine.
#
#   .workspace/scripts/daily.sh [--dry-run] [--since '24 hours ago']
#
# Point your Claude `/schedule` routine at this script. It runs the status
# pipeline and lands the result on `main` — the one piece `run.py` deliberately
# does not do, because locally the uncommitted diff is the review surface.
#
# WHY A SIDE BRANCH: the GitHub App identity a remote routine runs under cannot
# push to the default branch. The failure is misleading — the local git proxy
# reports a "non-fast-forward" error rather than a permission error — so the run
# pushes `auto/status-YYYY-MM-DD` instead, and
# .github/workflows/auto-merge-status.yml fast-forwards it onto main and deletes
# the branch.
#
# It commits ONLY the routine-owned files: summary.md, daily-plan-summary.md,
# and .workspace/state/. Never a child repo (the allowlist blocks that anyway),
# never your plans or repos.yml — those are yours, and a routine that quietly
# committed your working edits would be a trap.
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$WORKSPACE_ROOT"

DATE=$(date -u +%Y-%m-%d)
BRANCH="auto/status-$DATE"

# The routine sandbox is a fresh container; PyYAML may not be there. Install it
# only when it is actually missing, so a local invocation stays offline.
if ! python3 -c "import yaml" >/dev/null 2>&1; then
  echo "[daily] installing PyYAML"
  pip install --quiet pyyaml 2>/dev/null || pip install --user --quiet pyyaml
fi

# The sandbox has no ambient git identity. Fall back to the workspace's own
# git_author rather than failing at commit time, well after the work is done.
if ! git config user.email >/dev/null 2>&1; then
  author=$(python3 - <<'PY'
import pathlib, sys, yaml
cfg = yaml.safe_load(pathlib.Path(".workspace/config.yml").read_text()) or {}
a = cfg.get("git_author")
a = a if isinstance(a, str) else (a or [""])[0]
sys.stdout.write(str(a or ""))
PY
)
  [ -n "$author" ] || { echo "[daily] no git identity and no git_author in config.yml" >&2; exit 2; }
  git config user.email "$author"
  git config user.name "${author%%@*} (status routine)"
  echo "[daily] using git_author '$author' as the commit identity"
fi

git fetch origin
# -B, not -b: a re-run on the same day must reuse the branch rather than die on
# "already exists" after the work has already been done.
git checkout -B "$BRANCH"

python3 .workspace/scripts/run.py "$@"

# Explicit paths, not `git add -A`: the routine owns exactly these.
ROUTINE_FILES=(summary.md daily-plan-summary.md .workspace/state)
existing=()
for f in "${ROUTINE_FILES[@]}"; do [ -e "$f" ] && existing+=("$f"); done

if [ "${#existing[@]}" -eq 0 ]; then
  echo "[daily] the run produced no deliverables; nothing to push"
  exit 0
fi

git add -- "${existing[@]}"
if git diff --cached --quiet; then
  echo "[daily] no new work; nothing to push"
  exit 0
fi

git commit -q -m "status($DATE): daily rollup

- [Context]: scheduled status routine for $DATE.
- [Impact]: refreshes summary.md, daily-plan-summary.md, and the run state."

git push -u origin "$BRANCH"
echo "[daily] pushed $BRANCH — auto-merge-status.yml will fast-forward it onto main"
