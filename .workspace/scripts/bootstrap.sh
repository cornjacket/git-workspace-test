#!/usr/bin/env bash
# bootstrap.sh — reconstitute the workspace from repos.yml.
#
# Order matters: worktrees attach to a repo that must already exist, so we
# clone every `standard` repo first, then add every `worktree`.
# Idempotent: anything already present is skipped, so it is safe to re-run.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log() { printf '\033[1m==>\033[0m %s\n' "$*"; }

# ---------------------------------------------------------------------------
# Phase 1 — standard clones (must land before their worktrees attach).
# ---------------------------------------------------------------------------
log "Phase 1: cloning standard repositories"
while IFS=$'\t' read -r name type path branch parent url tags; do
  [ "$type" = "standard" ] || continue
  dest="$WORKSPACE_ROOT/$path"
  # Worktree-safe existence check: .git may be a file, so test -e not -d.
  if [ -e "$dest/.git" ]; then
    echo "  skip   $name ($path) — already present"
    continue
  fi
  if [ -z "$url" ]; then
    echo "  ERROR  $name — type=standard but no url" >&2
    continue
  fi
  echo "  clone  $name -> $path"
  git clone "$url" "$dest"
  [ -n "$branch" ] && git -C "$dest" checkout "$branch"
done < <(parse_repos)

# ---------------------------------------------------------------------------
# Phase 2 — worktrees (attach to an already-present parent repo).
# ---------------------------------------------------------------------------
log "Phase 2: adding worktrees"
while IFS=$'\t' read -r name type path branch parent url tags; do
  [ "$type" = "worktree" ] || continue
  dest="$WORKSPACE_ROOT/$path"
  if [ -e "$dest/.git" ]; then
    echo "  skip   $name ($path) — worktree already present"
    continue
  fi
  if [ -z "$parent" ]; then
    echo "  ERROR  $name — type=worktree but no parent_repo_path" >&2
    continue
  fi
  parent_dir="$WORKSPACE_ROOT/$parent"
  if [ ! -e "$parent_dir/.git" ]; then
    echo "  ERROR  $name — parent_repo_path '$parent' not present (clone it first)" >&2
    continue
  fi
  echo "  add    worktree $path ($branch) <- $parent"
  # `git worktree add <path> <branch>` checks out an existing branch.
  # For a brand-new branch, add -b: `git -C "$parent_dir" worktree add -b "$branch" "$dest"`.
  git -C "$parent_dir" worktree add "$dest" "$branch"
done < <(parse_repos)

log "Bootstrap complete. Run .workspace/scripts/status.sh to verify."
