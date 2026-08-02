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
├── project/             the workspace's OWN task-system (triage — see below)
├── .workspace/          the wrapper's control plane (hidden)
│   ├── config.yml       identity: name · git_author · generator_version
│   ├── repos.yml        membership registry — what repos/worktrees live here
│   ├── plans/           daily plans (per-developer, not shared)
│   │   └── _workspace/  the workspace's own forward-looking plan
│   └── scripts/         the wrapper's verbs (see below)
└── <child repos>/       managed checkouts — ignored by git
```

### The scripts (run via `make`, or directly from `.workspace/scripts/`)

- `bootstrap.sh` — reconstitute the workspace from `.workspace/repos.yml`: clone
  every `standard` repo, then `git worktree add` every `worktree`. Idempotent.
  `repos.yml` is a *lockfile*, not a config file you author — the repo verbs
  write it, `bootstrap.sh` replays it onto a fresh machine.
- `status.sh` — branch + clean/dirty for every managed checkout.
- `guard.sh` — fails if a child repo, a `.git` dir, or a worktree `.git` pointer
  was staged into the wrapper index. Wire it in as a pre-commit hook.
- `replan.sh` — redraft `.workspace/plans/_workspace/daily-plan.md` from
  `project/tasks`. **Draft-only:** it writes the file and stops, never commits.
- `lib.sh` — shared `repos.yml` parser (python3 + PyYAML).

The status subsystem (Python, run via `make`):

- `run.py` — the daily run: summarize → aggregate → advance state.
  `make run` uses `claude -p`; `make run-dry` skips every LLM call and emits
  deterministic placeholders.
- `new-work.py` — what *you* committed per repo since the last run.
- `aggregate-plans.py` — rebuild `daily-plan-summary.md` from `.workspace/plans/`.
- `sync.py` — report which repos are readable. Read-only; it never clones.
- `_status_lib.py` — shared config/membership/git-telemetry helpers.

### The rollup is author-scoped

Every git read filters `--author` against `git_author` in `.workspace/config.yml`,
so the summary shows **only your own commits**. A repo a teammate advanced reads
as INACTIVE *for you* while `state.json` still tracks the real HEAD, so tomorrow's
window stays correct. This is why the run **hard-fails** on an unresolved
`git_author`: a wrong one produces a plausible-looking but empty rollup rather
than an error, which is the worst kind of failure.

Deliverables, both written by the run and **never** by `setup`/`update`:
`summary.md` (retrospective, newest day first) and `daily-plan-summary.md`
(forward-looking, workspace plan first). Dated snapshots land in
`.workspace/state/archive/`.

### The workspace task-system is a triage area

`project/tasks/` tracks work that belongs to **no single child repo** — inter-repo
chores, infrastructure, and ideas that do not have a repo home yet. Work flows
*downward* from here:

- An idea lands as a workspace task **before** it has a repo.
- A workspace task **graduates** when it earns one: add a subtask "create repo X",
  run the repo verb, then migrate the remaining work into that child repo's own
  task-system. (Cross-boundary moves are manual today — recreate in the child,
  close in the workspace.)
- Anything that clearly belongs to an existing child repo belongs in **that repo's**
  task-system, not here. This one is for the homeless work.

`.workspace/plans/_workspace/daily-plan.md` is that task state rendered as a plan.
It is **forward-looking only** — the workspace's own commits are meta-noise, so it
carries no retrospective git summary, unlike a child repo's plan. Plans live in
the workspace (not in the child repos) because they are *per-developer* intent:
each developer's own workspace holds their own plans, so two developers never
collide over one shared plan file.

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
