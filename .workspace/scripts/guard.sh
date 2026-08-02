#!/usr/bin/env bash
# guard.sh — protect the wrapper's git index from swallowing its children.
#
# Fails if anything that belongs to a child repo/worktree has been staged into
# the WRAPPER (parent) index:
#   1. a whole child repo staged as a gitlink        (mode 160000)
#   2. a `.git` directory or worktree `.git` pointer  (staged file path)
#   3. any file living under a managed repo/worktree  (path listed in repos.yml)
#
# Intended as a pre-commit hook and a manual check. Read-only; it never resets.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

cd "$WORKSPACE_ROOT"
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "guard: workspace root is not a git repo yet — nothing to check."
  exit 0
fi

fail=0
note() { printf '\033[31mGUARD FAIL:\033[0m %s\n' "$*" >&2; fail=1; }

# 1. Embedded repos staged as gitlinks. `git ls-files --stage` prints
#    "<mode> <sha> <stage>\t<path>"; mode 160000 == a committed subrepo pointer.
while IFS= read -r file; do
  [ -z "$file" ] && continue
  note "child repo staged as a gitlink (embedded repo): $file"
done < <(git ls-files --stage | awk -F'\t' '$1 ~ /^160000 /{print $2}')

# 2. Any staged path that is, or lives inside, a .git dir or a .git pointer file.
while IFS= read -r f; do
  [ -z "$f" ] && continue
  note ".git artifact staged into the parent index: $f"
done < <(git diff --cached --name-only | grep -E '(^|/)\.git($|/)' || true)

# 3. Any staged path that falls inside a managed repo/worktree path.
managed=()
while IFS=$'\t' read -r name type path branch parent url tags; do
  [ -n "$path" ] && managed+=("$path")
done < <(parse_repos)

if [ "${#managed[@]}" -gt 0 ]; then
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    for p in "${managed[@]}"; do
      case "$f" in
        "$p"|"$p"/*)
          note "content of managed repo '$p' staged into parent index: $f" ;;
      esac
    done
  done < <(git diff --cached --name-only)
fi

if [ "$fail" -eq 0 ]; then
  echo "guard: OK — no child repos, .git dirs, or worktree pointers staged."
fi
exit "$fail"
