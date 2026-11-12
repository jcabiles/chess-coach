# CLAUDE.md

Guidance for Claude Code when working in this repository. The repo facts, commands, constraints
and the ticket procedure every agent shares are in `AGENTS.md`:

@AGENTS.md

## Commit policy (IMPORTANT)

Commit only after a change is **implemented, verified, and reviewed** — never WIP.

1. **Implemented** — complete, not partial.
2. **Verified** — evidence seen, not assumed:
   - Python/API: `make check` passes.
   - Frontend/UI: exercised in the browser (Playwright or manual).
3. **Reviewed** — diff read for correctness; no debug artifacts left
   (`console.log`, `window.__dbg`, screenshots, `.playwright-mcp/`).

**Format:** Conventional Commits subject (`feat:`, `fix:`, `refactor:`, `docs:`,
`test:`, `chore:`); imperative, ≤ 50 chars; body explains *why* when non-obvious.
End every message with the `Agent-Vendor:` and `Agent-Model:` trailers (the git
hooks refuse a commit without them), then:
`Co-Authored-By: Claude <noreply@anthropic.com>`

The `Co-Authored-By` line names no model version on purpose: a version pinned in
this file is correct only until the next model ships. The `Agent-Model:` trailer
does not have that problem, because each commit fills it with the model that
actually wrote that commit.

**Before creating any new branch:** `git fetch origin` then `git status -sb`
(or `git log main..origin/main`) to confirm local `main` matches `origin/main`.
If behind, `git pull` (or `git merge origin/main`) before branching — never
branch off stale local `main`, it causes avoidable conflicts/merge noise later.

One logical change per commit. Claude may `git push` and open PRs (`gh pr
create`) autonomously on feature branches (not `main`) without asking first;
never force-push, never merge a PR, never push directly to `main`. If
verification fails or was skipped — say so and don't commit. Commits written by
Codex or Gemini are pushed only after Claude's review records them (the
`pre-push` hook enforces this).

## Environment notes

The Claude Code Bash **sandbox** may block network installs, socket `bind`, and
writes to `.git/`. Verify routes in-process via FastAPI `TestClient` when a live
server is unavailable.
