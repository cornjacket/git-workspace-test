#!/usr/bin/env bash
# pull.sh — the morning trigger: bring the routine's aggregates down.
#
#   .workspace/scripts/pull.sh [--bootstrap] [--quiet]
#
# The mirror of daily.sh. Overnight the remote routine writes summary.md and
# daily-plan-summary.md and lands them on main; this fast-forwards your local
# workspace onto that.
#
# --ff-only IS THE POINT. This runs unattended, so it has exactly two outcomes:
# advance cleanly, or stop and tell you. It never merges, never rebases, never
# forces — an unattended job that resolves history is a job that eventually
# destroys something at 6am while you are asleep.
#
# Diverged means your local workspace has commits the remote does not. Push them
# (that is the normal fix) and the next pull fast-forwards again. Keeping ahead
# of the routine — pushing your plan and repos.yml edits before it runs — is what
# keeps this boring.
#
# Exit codes: 0 up to date or fast-forwarded · 1 declined (diverged) · 2 misconfigured.
set -uo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$WORKSPACE_ROOT"

DO_BOOTSTRAP=0
QUIET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --bootstrap) DO_BOOTSTRAP=1; shift ;;
    --quiet)     QUIET=1; shift ;;
    -h|--help)   sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "pull: unknown option: $1" >&2; exit 2 ;;
  esac
done

say() { [ "$QUIET" -eq 1 ] || printf '[pull] %s\n' "$*"; }

# notify — reach the human even when this runs from cron/launchd with no
# terminal attached. Always writes stderr too, so a log still shows it.
notify() {
  local title=$1 msg=$2
  printf '[pull] %s: %s\n' "$title" "$msg" >&2
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"${msg//\"/}\" with title \"${title//\"/}\"" \
      >/dev/null 2>&1 || true
  elif command -v notify-send >/dev/null 2>&1; then
    notify-send "$title" "$msg" >/dev/null 2>&1 || true
  fi
}

git rev-parse --git-dir >/dev/null 2>&1 || { echo "pull: not a git repo: $WORKSPACE_ROOT" >&2; exit 2; }
git remote get-url origin >/dev/null 2>&1 || {
  echo "pull: no 'origin' remote — nothing to pull." >&2
  echo "      Add one with: git remote add origin <url>" >&2
  exit 2
}

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
[ "$branch" != "HEAD" ] || { echo "pull: detached HEAD — check out a branch first." >&2; exit 2; }

if ! git fetch --quiet origin 2>/dev/null; then
  notify "Workspace pull failed" "could not reach origin"
  exit 2
fi

upstream="origin/$branch"
git rev-parse --verify --quiet "$upstream" >/dev/null || {
  echo "pull: $upstream does not exist — push this branch first." >&2
  exit 2
}

local_head=$(git rev-parse HEAD)
remote_head=$(git rev-parse "$upstream")

if [ "$local_head" = "$remote_head" ]; then
  say "already up to date"
else
  behind=$(git rev-list --count "HEAD..$upstream")
  ahead=$(git rev-list --count "$upstream..HEAD")
  if [ "$ahead" != "0" ]; then
    # Diverged, or purely ahead. Either way there is nothing to fast-forward TO
    # without discarding or merging, so stop and hand it back to the human.
    if [ "$behind" = "0" ]; then
      notify "Workspace is ahead of origin" \
        "$ahead local commit(s) not pushed. Run: git push origin $branch"
    else
      notify "Workspace pull declined" \
        "diverged: $ahead local / $behind remote commit(s). Reconcile by hand."
    fi
    exit 1
  fi
  if ! out=$(git merge --ff-only "$upstream" 2>&1); then
    notify "Workspace pull declined" "fast-forward refused: $(printf '%s' "$out" | tail -1)"
    exit 1
  fi
  say "fast-forwarded $behind commit(s) from $upstream"
  # Name what actually arrived — the whole point of the morning pull.
  for f in summary.md daily-plan-summary.md; do
    if git diff --name-only "$local_head..HEAD" -- "$f" | grep -q .; then
      say "updated $f"
    fi
  done
fi

# A repo added to repos.yml on another machine arrives as a registry entry with
# no checkout; bootstrap materializes it. Opt-in because it clones.
if [ "$DO_BOOTSTRAP" -eq 1 ]; then
  say "materializing any newly registered repos"
  "$(dirname "${BASH_SOURCE[0]}")/bootstrap.sh"
fi
exit 0
