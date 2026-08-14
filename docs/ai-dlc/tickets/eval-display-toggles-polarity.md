# Ticket — Analysis panel: two plain "show this" switches

status: approved  # owner go-gate, 2026-08-06

## Why

PR #73 shipped a "Hide evaluation score" checkbox directly above the existing
"Win-chances bar" checkbox. The two are adjacent and mean **opposite things** —
ticking one shows a thing, ticking the other hides a thing. The owner tried to turn
the score off by unticking it and got the score back. Ticking a box must mean
"show this."

## Target design (owner-approved, 2026-08-06)

Two **independent, always-visible** checkboxes in `#analysis-settings-body`, both
positive polarity, neither forcing the other:

```
Evaluation score   [ ]    ticked = the numeric #eval readout is shown
Win-chances bar    [ ]    ticked = the #eval-bar is shown
```

1. **Positive polarity.** Ticked = visible. No "hide" wording anywhere in the labels.
2. **Independent.** Neither disables, greys out, or overrides the other. **No checkbox
   is ever `disabled`** — delete the forced/disabled/title machinery entirely.
3. **Always visible.** The "Evaluation score" row no longer appears only in
   Blunders-only; both rows are permanently in the settings body.
4. **Per-mode remembered state (two buckets).** The checkboxes read and write the
   bucket for the current analysis mode:
   - bucket `blunders` → defaults **both unticked** (this is the anti-cheat default);
   - bucket `default` (used by Full **and** Off) → defaults **both ticked**.
   Switching analysis mode swaps which bucket the checkboxes reflect, updates their
   `.checked`, and re-syncs the display. Each bucket persists independently, so the
   owner's Full-mode setup survives a trip through Blunders-only and back.
5. **Play-scoped.** Both switches apply only while `state.mode` is `'play'` or
   `'bot-play'`. Review replay, trap practice, repertoire and the trainers **always**
   show the score and the bar regardless of these settings. (This is a deliberate
   change for the bar, which is currently global.)
6. **Mode switching is not a leak.** Under this design, moving Blunders-only → Full
   or → Off legitimately reveals the eval, because the user asked for it explicitly.
   Delete `evalDisplaySuppressed` and the Off-retention logic that existed only to
   stop that reveal.

## Migration

Read the legacy keys once when the new shape is absent, so the owner keeps their
current setup: `evalBarHidden === true` → `default` bucket bar = `false`;
`blundersHideEval === false` → `blunders` bucket score = `true`. Legacy keys are then
no longer written.

## Boundaries

- The bar keeps painting its **true fill** at all times (`setEvalBar(evalBarFill(a))`
  stays unconditional). Never write a fabricated neutral value into a bar that can
  become visible — a lying bar is worse than a hidden one. This was a defect in
  PR #73's review history; do not reintroduce it.
- `panel.js` must still know nothing about `analysisMode`; app.js threads booleans in.
  The `suppressEval` threading through `renderSecond` / `renderRetroBlock` /
  `renderSkippedPanel` stays — the score annotations on the 2nd-best and retro lines
  (`· or Qe2 (-3.35)`) are part of "the evaluation score" and must hide with it.
- The play-scope gate + `on('mode:change', …)` re-sync pattern from PR #73 stays; it is
  what keeps review/traps unaffected.
- Tokens-only CSS, AA contrast, `:focus-visible`, no raw hex. Reuse
  `.eval-bar-toggle-row`.

## Acceptance

1. Fresh profile, Full mode → both boxes ticked; number and bar both visible.
2. Switch to Blunders-only → both boxes **untick themselves**; number and bar both hidden.
3. Tick "Evaluation score" in Blunders-only → number appears, bar stays hidden.
   Tick "Win-chances bar" → bar appears. Neither is ever greyed out.
4. Set Full mode's boxes to (score on, bar off) → visit Blunders-only → return to Full:
   still (score on, bar off).
5. In Blunders-only with both unticked, a flagged blunder still shows the Blunder badge
   and the best move, with **no** number anywhere — including no `(-3.35)` on the
   2nd-best or retro lines.
6. Open a saved game in Review with both unticked in Blunders-only → review shows the
   number **and** the bar. Same for trap practice. Returning to play re-hides them.
7. Off mode uses the `default` bucket (both ticked by default) and keeps its freeze
   behaviour.

## Known, accepted

On a **cold** review fetch there is a theoretical window where the win-chances
bar un-hides on entering review before `renderReplayEval()` has data, briefly
showing the play game's fill. Sampled every 120ms in the browser and could not
reproduce it (the review panel painted its own value at the first sample). Not
fixed deliberately — the obvious quick fix (painting a neutral 50 before the
fetch) would reintroduce the fabricated-value bar that a previous review round
removed, and a lying bar is worse than a brief stale one.

The equivalent window for the numeric readout (`#eval`) AND the 2nd-best/retro
score annotations (`.line-eval`) IS fixed: `enterReview` resets `#eval`'s text
to `'—'` and blanks every `.line-eval` span immediately after `setMode('review')`,
so a failed `/review` fetch, or one deferred by `awaitAnalysisThenLoad`'s poll
(`renderReplayEval` never runs, or not for a while), shows the honest "no
value" state instead of leaking the play game's stale number/annotations for
the rest of the session. That reset is text-only and does not touch
`setEvalBar` — a neutral bar fill would be the same fabricated-value mistake
called out above, just moved to the number's sibling control.

## Done-condition

`.venv/bin/python -m pytest -q` green · `.venv/bin/ruff check app tests` clean ·
`node --check` on both JS files · no console errors on boot.
