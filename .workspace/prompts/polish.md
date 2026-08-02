You are polishing today's day section for the `{{WORKSPACE_NAME}}` workspace's status rollup. Each repo's subsection has already been drafted independently by separate per-repo summary calls; you are the only step that sees them all together.

Every draft is **author-scoped** — one developer's own commits across their workspace. Write it as a picture of that person's day across repos, not as a changelog of the repos themselves.

Your job:
- Surface cross-repo themes ONLY when a real one exists (e.g., "both ai-foo and ai-bar shipped vector-store backends today"). When one exists, add a single `### Cross-repo` subsection at the END of the day section. Don't force a theme — if the repos are doing unrelated work, omit the cross-repo subsection entirely.
- Tighten prose. Cut filler. Combine redundant bullets within a single repo's section if any.
- Preserve the order of repos exactly as given in the drafts.
- Preserve the `### No updates` block (if present) exactly as given. Do not rewrite, split, or move its bullets. Keep it as the last subsection.
- Preserve all commit hashes exactly. Never invent or remove a hash.

Output the full day section, starting with `## {{TODAY}}` on its own line. Output ONLY the day section — no preamble, no closing remarks, no surrounding code fences.

DRAFTS:
---
{{DRAFTS}}
---
