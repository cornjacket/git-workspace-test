# CLAUDE.md — git-workspace-test

<!-- Anything you write OUTSIDE the managed block below is yours and is preserved
     across updates. create-git-workspace regenerates ONLY the block between the
     two git-workspace markers. Put your own directives above or below it. -->

<!-- git-workspace:begin — managed by create-git-workspace; do not edit inside this block -->

## Workspace machinery (managed)

This repo is a **git-workspace**: a wrapper that *manages a set of other repos*
(and worktrees) sitting beside it. Its machinery lives in a hidden `.workspace/`
directory; only this `CLAUDE.md` (and `README.md`) sit at the top level. An
allowlist `.gitignore` tracks only that machinery and ignores every managed child
repo/worktree, so the wrapper can never accidentally swallow them.

The wrapper manages the *set* of repos; it does not edit their contents.

### Layout

```
git-workspace-test/
├── CLAUDE.md            this file (visible entry point)
├── README.md            what this workspace is + the daily dashboard links
├── Makefile             visible command surface: make status | bootstrap | guard
├── .gitignore           allowlist: tracks .workspace/ + the top-level files
├── .workspace/          the wrapper's control plane (hidden)
│   ├── config.yml       identity: name · git_author · generator_version
│   ├── repos.yml        membership registry — what repos/worktrees live here
│   └── scripts/         the wrapper's verbs (see below)
└── <child repos>/       managed checkouts — ignored by git
```

### The scripts (run via `make`, or directly from `.workspace/scripts/`)

- `bootstrap.sh` — reconstitute the workspace from `.workspace/repos.yml`: clone
  every `standard` repo, then `git worktree add` every `worktree`. Idempotent.
- `status.sh` — branch + clean/dirty for every managed checkout.
- `guard.sh` — fails if a child repo, a `.git` dir, or a worktree `.git` pointer
  was staged into the wrapper index. Wire it in as a pre-commit hook.
- `lib.sh` — shared `repos.yml` parser (python3 + PyYAML).

### Rules for any agent working here

- **`cd` into the target child repo/worktree first.** Run every git/build command
  from *inside* `<path>` — never from the wrapper root. Operating on a child from
  the root risks hitting the wrong repo or staging a child into the wrapper index
  (exactly what `guard.sh` catches).
- **A worktree's `.git` is a FILE, not a directory** — it points into the parent's
  `.git/worktrees/...`. To detect a checkout, test **`[ -e <path>/.git ]`**
  (exists), never `[ -d <path>/.git ]` (is-directory) — the `-d` form silently
  misses every worktree.
- **Do real code work inside the owning child repo**, from a session rooted there
  — not from this wrapper.

Two checkout kinds are declared in `.workspace/repos.yml`: **standard** (a normal
clone) and **worktree** (a linked worktree; `parent_repo_path` names the repo it
hangs off).

### What regeneration owns

`.workspace/scripts/`, `.gitignore`, `Makefile`, and this block are **machinery**:
`update.sh` overwrites them, so edits are lost. `.workspace/repos.yml`,
`.workspace/config.yml`, `README.md`, and anything you write *outside* these
markers are **content** — never overwritten.

_Managed block from create-git-workspace v0.1.0; canonical version
lives in `.workspace/config.yml`. Refresh with the generator's `update.sh`._

<!-- git-workspace:end -->
