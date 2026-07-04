# Tickets — UX Refinement (consistency + light theme + Insights redesign + mobile)

6 tickets, serial DAG (single Fable high-effort `ux-ui-designer` worker per user
directive; `style.css`/`index.html` are single-owner per ticket — no parallel edits).
Each ticket runs the build loop: **ux-ui-designer → boot (uvicorn :8001) →
design-reviewer → iterate (max 3)** before the next starts. Spec:
`docs/ai-dlc/specs/ux-refinement-ux.md`; contracts: `docs/ai-dlc/contracts/ux-refinement-ux.md`.

```
T1 theme foundation ─► T2 review sweep ─► T3 insights redesign ─► T4 mobile ─► T5 polish ─► T6 verify+commit
```

---

### T1 — Theme foundation: light palette, toggle, token completion (spec §A+§B)
**Owns:** `static/style.css`, `static/index.html` (head inline script + header toggle
button), NEW `static/theme.js`, `static/panel.css` (eval-bar token lines only).
**Does:** pre-paint inline `<head>` script (reads `chess-training:ui:v1` → `theme`,
resolves `system` via matchMedia, sets `html[data-theme]`); `theme.js` toggle module
(cycles system→light→dark, Lucide sun/moon/monitor, persists via `writeUiPref`,
matchMedia handler no-ops unless stored pref is `'system'`); light token block
`html[data-theme="light"]` overriding surfaces/borders/text/accent trio/error/quality
ramp/shadows/scrim **and all new derived tokens**; `color-scheme` = `dark light` (root) /
`light dark` (light block) — both values always; new tokens `--eval-bar-black/white`
(theme-independent) applied at `panel.css:20,31`; `--q-*-dim`, `--accent-dim-hover`,
`--q-blunder-border`, `--shadow-toast` DEFINED (dark + light values; review.css swap is
T2's); delete dead `--bg`/`--panel-bg`.
**Acceptance:** toggle cycles + persists across reload; system mode follows OS; no FOUC
on hard reload any stored state; pieces render correctly (not inverted) in light theme
under OS-dark; every surface AA in both themes; each `-dim` token AA against its paired
text color.
**Done-condition:** `pytest -q` green; grep gate clean for `style.css`/`panel.css`
(raw colors only in token blocks); Playwright: toggle through 3 states → reload each →
correct theme, 0 console errors, screenshot dark+light @1440; design-reviewer pass.
**Deps:** none.

### T2 — Review-surface consistency sweep (spec §B swap + §C)
**Owns:** `static/review.css`, `static/app.js` (ONLY deleting orphaned
`classList.toggle('review-mode', on)` at :1842).
**Does:** swap the 7 raw `oklch()` literals in `review.css` to T1's tokens
(281-283, 346, 351, 356, 790→`--shadow-toast`); normalize `:focus` → `:focus-visible`
+ standard `outline: 2px solid var(--accent)` at 411, 448, 734 (drop `outline: none`);
add reduced-motion override for `@keyframes review-toast-in`; border-diet pass on
review cards/lists (spacing + elevation over box-lines, hairlines only where needed).
**Acceptance:** review tab visually consistent with design system in BOTH themes;
badges/buttons readable (paired contrast); keyboard focus visible on all review controls;
no behavior change.
**Done-condition:** `pytest -q` green; grep gate clean for `review.css`;
`grep -n 'review-mode' static/` → zero hits; Playwright: review tab dark+light, tab-key
walk shows focus rings, 0 console errors; design-reviewer pass.
**Deps:** T1 (tokens must exist).

### T3 — Insights deep redesign + signature motion (spec §D)
**Owns:** `static/insights.css`, `static/insights.js` (markup inside render functions
ONLY — no fetch/data-read changes).
**Does:** data-viz identity: coverage stat blocks; win-rate horizontal bars
(token-colored, tabular-nums); adherence/theory metric rows; cluster ranked cards with
quality-color accents; time-trouble mini bar row; signature animate-in (staggered
fade/slide + bar-fill sweep) on first build only via existing `_shellBuilt`/
`_mistakesLoaded` guards (refuter-verified: render fns run exactly once per page load);
reduced-motion → instant; border-diet.
**Acceptance:** all sections render with real + thin data; per-metric min-sample gating
lines preserved per-metric ("one long-run trend, always visually secondary"); deep-link
button still calls `openGameAtPly(gameId, ply)` and enters review at correct ply; all
`#insights-*` IDs + role/`.is-active` pattern intact; JSON reads byte-identical
(`book_exit_ply===0` sentinel, `'<10s'` literal, `clusterDisplayName` strip untouched);
animation plays once, not on sub-tab switch.
**Done-condition:** `pytest -q` green; `git diff static/insights.js` shows no changes to
fetch calls or data-key reads; Playwright: open Insights → both sub-tabs render, switch
back/forth (no re-animation), deep-link jumps to review, dark+light @1440, 0 console
errors; design-reviewer pass.
**Deps:** T1 (tokens/themes).

### T4 — Mobile 375 pass (spec §E)
**Owns:** `static/style.css` (breakpoint tiers, touch targets), `static/movelist.css`
(mobile hit-box).
**Does:** fix the real 24px overflow: board `calc(92vw - 22px)` (or flex-yield) at
≤560px, eval-bar min-height matched; touch targets ≥24×24 on all interactive controls;
enlarge `.trap-chip-dismiss`, `.rep-line-practice`; `.movelist-move` mobile-only
(≤820px) padding to ≥24px computed height (desktop density unchanged); mode bars wrap
cleanly; check 561–820px band for visible breaks.
**Acceptance:** at exactly 375px: zero horizontal overflow on every tab + every mode
bar (setup/trap/review/rep), both themes; all targets ≥24px on mobile.
**Done-condition:** Playwright @375: iterate all 6 tabs + 4 mode bars,
`document.documentElement.scrollWidth <= 375` each, tap-target audit of named controls,
screenshots dark+light; 0 console errors; design-reviewer pass @375.
**Deps:** T1 (style.css owner), ideally after T3 (insights layout final before mobile
verify).

### T5 — App-wide polish remainder (spec §C rest)
**Owns:** `static/style.css`, `static/index.html` (stepper glyphs), `static/feedback.css`.
**Does:** trap-stepper ⏮◀▶⏭ → Lucide ChevronFirst/Left/Right/Last (chess-piece
glyphs STAY — domain notation); border-diet on remaining surfaces (panel tabs, trainer
lists, setup bar); empty/loading/microcopy consistency (`.empty-state` stays owned by
`style.css:546`, never redefined); final icon/label audit — no emoji as UI icons.
**Acceptance:** app-wide visual consistency both themes; stepper works identically with
new icons (aria-labels kept); no regression in trap/rep/setup flows.
**Done-condition:** `pytest -q` green; Playwright: walk all 6 tabs + trap watch/practice
+ rep practice + setup mode, dark+light @1440, 0 console errors; design-reviewer pass.
**Deps:** T1, T4 (style.css owner sequence).

### T6 — Full verify + review + commit (spec Verify-by, orchestrator)
**Owns:** cross-cutting glue only (small fixes surfaced by the matrix); commits.
**Does:** full Verify-by matrix: pytest + ruff; grep gate all CSS; Playwright
{dark, light} × {375, 1440} × 6 tabs + 4 mode bars; FOUC hard-reload checks ×3 stored
states; reduced-motion emulation; insights once-only animation + deep-link; AA contrast
spot-checks both themes; final screenshots (all in-scope pages, both breakpoints+themes)
**shown to user in completion report**; independent reviewer (maker ≠ checker) on the
full diff; remove debug artifacts; shut dev server; commit series per policy
(Conventional Commits, logical grouping: theme foundation → review sweep → insights →
mobile → polish).
**Acceptance:** every spec Verify-by item green; review clean; commits made (not pushed
to main; feature branch).
**Done-condition:** verify matrix all green; `git log` shows the commit series;
screenshots delivered.
**Deps:** T1–T5.

---

## Build-loop rules (per ticket, from /ai-dlc-ux-ui §5)
- Designer = `ux-ui-designer` (Fable, high effort — user-authorized single worker);
  reviewer = `design-reviewer`; designer NEVER self-approves.
- Boot: `uvicorn app.main:app --reload --port 8001` (sandbox blocks bind → run in
  user terminal or disable sandbox for the boot command; Playwright-MCP against
  http://localhost:8001).
- Max 3 design→review iterations per ticket; still failing → stop, surface issues.
- Deterministic gates after each ticket: `pytest -q`, grep gate, 0 console errors.
