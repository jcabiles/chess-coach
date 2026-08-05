# Tickets — Blunders-only: hide the evaluation score

status: approved  # owner go-gate, 2026-08-05 — no Fable, no Terra

## Why

Blunders-only mode exists so a bot game gets a disaster warning and nothing else.
A live evaluation score (the `#eval` readout AND the win-chances bar) defeats that —
it is a continuous cheat code. This adds an opt-out toggle, ON by default in
Blunders-only mode.

## Decisions (owner-approved, 2026-08-05)

1. **Hides both surfaces** with one switch: the numeric `#eval` readout and the
   `#eval-bar` win-chances bar.
2. **Default = hidden** whenever Blunders-only is the active mode.
3. **Sub-setting of Blunders-only:** the checkbox is only visible/effective while
   mode === `'blunders'`. Full/Off are unaffected.
4. **No reveal on blunder.** Unlike best-move + PV (which reappear on a flagged
   blunder), the score stays hidden for every move — blunder, checkmate and draw
   included. You get a warning, never a number.
5. **Bar precedence:** while forced-hidden, the existing `#eval-bar-visible`
   checkbox is `disabled` and renders unchecked, but its `evalBarHidden` pref is
   **never rewritten**. Leaving the state restores the user's own choice.

## Boundaries

- `analysisOpts()` is the **play-path-only** filter (`static/app.js:925`). Review
  replay (`hub.renderAnalysis`) and trap practice (direct `renderAnalysisPanel`
  calls) must NOT inherit the suppression. Do not put a mode flag inside `panel.js`.
- Engine behavior unchanged: Blunders-only still evaluates every move. This is a
  display filter only — do not skip analysis calls.
- Tokens-only CSS, AA contrast, `:focus-visible`. Reuse the existing
  `.eval-bar-toggle-row` label pattern; add no new hex.

## T1 — Implement the toggle end-to-end

- **Owns:** `static/app.js`, `static/panel.js`, `static/index.html` (all three are
  hotspots → **one owner, no concurrent worker**), `static/panel.css` only if the
  existing row class genuinely cannot be reused.
- **Do:**
  1. `static/index.html` — inside `#analysis-settings-body`, after
     `.analysis-mode-row` and before the `Win-chances bar` label, add a row:
     `<label class="eval-bar-toggle-row" id="blunders-hide-eval-row">` with
     `<span class="eval-label">Hide evaluation score</span>` and
     `<input type="checkbox" id="blunders-hide-eval" checked>`.
  2. `static/app.js` — new persisted pref `blundersHideEval` via
     `readUiPrefs()` / `writeUiPref()`, **defaulting to `true` when absent**
     (`readUiPrefs().blundersHideEval !== false`).
  3. `static/app.js` — `analysisOpts(a)`: when
     `analysisMode === 'blunders' && blundersHideEval`, every returned opts object
     (including the `blunder` / `checkmate` / `draw` early return and the
     non-blunder object) carries `suppressEval: true`. Full/Off unchanged.
  4. `static/panel.js` — `renderAnalysisPanel`: when `opts.suppressEval` is truthy,
     paint `#eval` as `'—'`. **Final rule (after two reversals):** `setEvalBar()`
     keeps painting the real fill underneath the CSS hide, unconditionally — never
     a fabricated neutral 50. A neutral-fill fallback was tried and reverted: it
     made the bar visibly WRONG (not just hidden) across the Off transition —
     `--fill: 50.00%` painted over every suppressed render, then stayed frozen at
     that fake value once Off's freeze branch stopped repainting — and briefly
     wrong on every un-hide in play, flashing 50% before `refreshAnalysis()`'s
     round-trip (0.37-2.8s) landed the truth. The invariant is: the bar is either
     hidden, or truthful, never visible while holding a neutralized value. Since
     the true fill is always painted, the ONLY way to honor that invariant is to
     keep the bar's CSS-hide class held through the Off transition — see the
     `evalDisplaySuppressed` flag in step 5. Do not touch `renderBookMovePanel` /
     `renderSkippedPanel`'s own `'—'` text, but do thread `hideEval` through
     `renderSkippedPanel`'s carried-retro path (its 2nd-best line can otherwise
     leak a carried blunder's score).
  5. `static/app.js` — extend the existing `syncEvalBarHidden()` to compute a
     `forced` flag, gated to play/bot-play:
     `(state.mode === 'play' || state.mode === 'bot-play') &&
     ((analysisMode === 'blunders' && blundersHideEval) ||
      (analysisMode === 'off' && evalDisplaySuppressed))`.
     `evalDisplaySuppressed` is a module-level flag, seeded at boot from
     `analysisMode === 'blunders' && blundersHideEval`, and maintained ONLY from
     mode transitions (never derived at render time): entering `'blunders'` sets
     it to `blundersHideEval`; entering `'full'` clears it; entering `'off'`
     leaves it **unchanged** — that retention is what keeps the bar's CSS-hide
     class held through the Blunders→Off transition instead of revealing the
     true (never-neutralized, per step 4) fill. The hide-eval checkbox's `change`
     handler also sets it to the checkbox's new value (only reachable in
     `'blunders'`). Every setter is followed by `syncEvalBarHidden()`.
     - `.board-wrap` gets `eval-bar-hidden` when `evalBarHidden || forced`;
     - `#eval-bar-visible` → `.checked = !(evalBarHidden || forced)` and
       `.disabled = forced`, with a `title` naming the cause;
     - the bar checkbox's `change` handler still writes only `evalBarHidden`.
  6. `static/app.js` — `syncAnalysisMode()` shows/hides `#blunders-hide-eval-row`
     (mode === `'blunders'`) and syncs its `.checked`. The new checkbox's `change`
     handler writes the pref, calls `syncEvalBarHidden()`, bumps `analysisToken`
     and calls `refreshAnalysis()` **only when `state.mode` is `play`/`bot-play`**
     (same gate `setAnalysisMode` uses — never hit the live engine during review
     replay). `setAnalysisMode` must also call `syncEvalBarHidden()` so switching
     modes flips the bar.
- **Acceptance:**
  - Blunders-only + toggle on → `#eval` reads `'—'` and the bar is not visible, on a
    quiet move AND on a flagged blunder (the Blunder badge + best move still show).
  - Unchecking the toggle → number and bar both return live, without a page reload.
  - Switching to Full → number + bar return, `#eval-bar-visible` re-enabled and
    reflecting its own saved pref; the row disappears.
  - Setting "Win-chances bar" off in Full, then entering Blunders-only, then leaving
    → the bar is still off (its pref was not overwritten).
  - Review replay and trap practice show evals normally in every mode.
- **Done-condition:** `.venv/bin/python -m pytest -q` green and
  `.venv/bin/ruff check app tests` clean (regression guard — this is a
  frontend-only change), plus no console errors on boot.

## T2 — Adversarial review (maker ≠ checker)

- **Owns:** nothing (read-only).
- **Do:** Review the T1 diff for contract violations: review-replay/trap-practice
  leakage, the `evalBarHidden` pref being overwritten, a stale-render path that
  un-hides the number after an await, first-paint order (pref applied before the
  first `renderAnalysis`), and the `analysisToken` invalidation being skipped.
- **Depends on:** T1.

## T3 — Browser verification (Playwright-MCP, live server)

- **Owns:** nothing.
- **Do:** Exercise all five acceptance bullets in a real browser at both themes;
  confirm zero console errors and `:focus-visible` on the new checkbox.
- **Depends on:** T1 (runs concurrently with T2).
