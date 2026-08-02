#!/usr/bin/env bash
# replan.sh — redraft the WORKSPACE's own daily plan from its task state.
#
#   .workspace/scripts/replan.sh [--date YYYY-MM-DD]
#
# The workspace plan (.workspace/plans/_workspace/daily-plan.md) covers work that
# belongs to no single child repo: inter-repo chores, infrastructure, and ideas
# that do not have a repo home yet. It is FORWARD-LOOKING ONLY — the workspace's
# own commits are meta-noise, so unlike a child repo's plan it has no
# retrospective git-log half.
#
# TWO INVARIANTS, both load-bearing:
#
#   * Draft-only. This writes the plan file and stops. It never stages, never
#     commits, never pushes. Git is the review surface: the redrafted plan shows
#     up as a modified file, and approving it means committing it yourself.
#   * The plan is DERIVED from task state, not invented. You encode intent by
#     curating project/tasks; this script reads that state. It never edits tasks.
#
# Section ownership mirrors the rest of this generator: the derived sections
# (In progress / Next up / Triage) are rewritten every run, and everything from
# `## Notes` onward is yours and is preserved verbatim.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

PLAN="$WORKSPACE_DIR/plans/_workspace/daily-plan.md"
TASKS="$WORKSPACE_ROOT/project/tasks"
DATE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --date) DATE=${2:-}; shift 2 ;;
    -h|--help) sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "replan: unknown option: $1" >&2; exit 2 ;;
  esac
done

[ -n "$DATE" ] || DATE=$(date +%Y-%m-%d)
case "$DATE" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
  *) echo "replan: --date must be YYYY-MM-DD, got '$DATE'" >&2; exit 2 ;;
esac

if [ ! -d "$TASKS" ]; then
  echo "replan: no task-system at $TASKS." >&2
  echo "        The workspace plan is derived from it — install one by re-running" >&2
  echo "        the generator's setup.sh without --no-tasks." >&2
  exit 1
fi

# list_folder <status> — task ids in that status folder, one per line.
# Reads the task-system's own lister rather than globbing directories, so the
# folder layout stays that generator's business.
list_folder() {
  "$TASKS/scripts/list-tasks.sh" --folder "$1" --depth 1 --all 2>/dev/null \
    | sed -n 's/^    \([^ ].*\)$/\1/p'
}

bullets() { # <heading-fallback>
  local any=0 line
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    any=1
    printf -- "- [ ] %s\n" "$line"
  done
  [ "$any" -eq 1 ] || printf -- "%s\n" "$1"
}

tmp=$(mktemp "${TMPDIR:-/tmp}/replan.XXXXXX")
{
  printf '# Daily plan — %s\n\n' "$DATE"
  printf '_Workspace-scoped work: inter-repo tasks, infrastructure, and ideas that have no\n'
  printf 'repo home yet. Forward-looking only — the workspace'"'"'s own commits are meta-noise,\n'
  printf 'so this plan has no retrospective half._\n\n'
  printf '_Derived from `project/tasks` by `make replan`. Draft only: review the diff and\n'
  printf 'commit it yourself._\n\n'

  printf '## In progress\n\n'
  list_folder in-progress | bullets "_Nothing in progress._"
  printf '\n## Next up\n\n'
  list_folder backlog | bullets "_Nothing queued._"
  printf '\n## Triage\n\n'
  { list_folder inbox; list_folder draft; } | bullets "_Nothing in triage._"
  printf '\n_A workspace task graduates when it earns a repo: add a subtask "create repo X",\n'
  printf 'run `add-repo`, then migrate the remaining work into that child'"'"'s task-system._\n'

  # Preserve the human's half verbatim, or start one.
  if [ -f "$PLAN" ] && grep -q '^## Notes' "$PLAN"; then
    printf '\n'
    sed -n '/^## Notes/,$p' "$PLAN"
  else
    printf '\n## Notes\n\n'
    printf '_Everything below the Notes heading is yours — `replan` never rewrites it._\n'
  fi
} > "$tmp"

mkdir -p "$(dirname "$PLAN")"
if [ -f "$PLAN" ] && cmp -s "$tmp" "$PLAN"; then
  rm -f "$tmp"
  echo "replan: plan already current — nothing changed."
  exit 0
fi
mv "$tmp" "$PLAN"

printf '\033[1m==>\033[0m redrafted %s\n' "${PLAN#$WORKSPACE_ROOT/}"
printf '    review it (git diff) and commit it yourself — replan never commits.\n'
