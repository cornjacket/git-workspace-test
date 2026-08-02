#!/usr/bin/env bash
# status.sh — show the current branch + working-tree state for every managed
# repo and worktree in repos.yml. Read-only.
#
# Exit non-zero if anything is missing or dirty (usable as a pre-flight check).
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if [ -t 1 ]; then
  B=$'\033[1m'; D=$'\033[2m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; X=$'\033[0m'
else
  B=""; D=""; G=""; Y=""; R=""; X=""
fi

printf "%b%-34s %-10s %-20s %s%b\n" "$B" "NAME" "TYPE" "BRANCH" "STATE" "$X"
rc=0
while IFS=$'\t' read -r name type path branch parent url tags; do
  dest="$WORKSPACE_ROOT/$path"
  # Worktree-safe: .git is a FILE for worktrees, so test -e (exists), not -d.
  if [ ! -e "$dest/.git" ]; then
    printf "%-34s %-10s %-20s %bmissing%b\n" "$name" "$type" "-" "$R" "$X"
    rc=1
    continue
  fi
  cur=$(git -C "$dest" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
  if [ -z "$(git -C "$dest" status --porcelain 2>/dev/null)" ]; then
    state="${G}clean${X}"
  else
    dirty=$(git -C "$dest" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    state="${Y}dirty (${dirty})${X}"
    rc=1
  fi
  printf "%-34s %-10s %-20s %b\n" "$name" "$type" "$cur" "$state"
done < <(parse_repos)

exit $rc
