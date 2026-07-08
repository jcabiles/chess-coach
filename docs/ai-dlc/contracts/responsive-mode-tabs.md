# Contracts — responsive-mode-tabs (special-mode tab lock)

Read-only scan of the mode-exit wiring. Source: `contract-mapper`, 2026-07-07.

## Root cause
`static/app.js:896` — inside the `#panel-tabs` click handler:
`if (document.body.dataset.mode !== 'play') return;` silently drops tab clicks in
any non-play mode. Only escape today = per-mode "Return to my game" button.

## Exit wiring per mode
| Mode | Exit fn | Registered via `registerModeHandlers`? | Button |
|---|---|---|---|
| setup | `cancelSetup` (setup.js:198) | Yes — setup.js:229 | `#cancel-setup` |
| trap-watch | `exitTrap` (traps.js:401) | Yes — traps.js:735 | `#trap-return` (shared) |
| trap-practice | `exitTrap` | Yes — traps.js:736 | `#trap-return` |
| rep-practice | `exitRepPractice` (repertoire.js:255) | Yes — repertoire.js:416 | `#rep-return` |
| blunder-practice | `exitTrainer` (trainer.js:585) | Yes — trainer.js:612 | `#trainer-return` |
| **review** | `exitReview` (**app.js:767**) | **No** — never registered | `#review-return` (app.js:972); also `api.actions.exitReview` (app.js:848), called cross-module from trainer.js:293 |

## Generic seam status
`ensurePlay()` (app.js:686) = `const h=_modeHandlers[state.mode]; if(h&&h.exit) h.exit();`
- Dispatches correctly for all **registered** modes.
- **No-op for review** (not registered) → this is the gap. trainer.js:293 already
  special-cases review (`if mode==='review' exitReview()`) precisely because
  `ensurePlay()` can't reach it.
- Exposed as `api.hub.ensurePlay` (app.js:866). No `requestModeExit()` today.

## Transient state on exit (cheap vs meaningful)
| Mode | State | Verdict |
|---|---|---|
| setup | board placement in `ground()` + `setupColor`; **no dirty tracking** | **Meaningful, undetectable** — cannot tell untouched from carefully-arranged. Silent discard = biggest regression risk. |
| trap-watch | `trap.step` (view pos) | Cheap — re-entry restarts at step 0 |
| trap-practice | `trap.step` (short scripted line, no persisted score) | Cheap-ish |
| rep-practice | `rep` (moves, tree node, engineMode, expected) | Moderately meaningful — longer engine session possible, no persisted score at stake |
| blunder-practice | `drill` (index, attempts, `results[]`, flushed) | **Meaningful + side effect**: `exitTrainer` calls `flushOutcomes()` → POST `/api/trainer/bucket-complete` (Leitner schedule). Resolved outcomes flushed on exit; only in-progress unresolved puzzle abandoned by design. **Generic exit MUST route through `exitTrainer` — never a raw `setMode('play')` — or the flush is skipped.** |
| review | `reviewSnapshot` (app.js:61) + stale `review.js` module vars (not cleared on exit) | Cheap — pure replay viewer, ply cursor only |

## Ordering
All six exit fns call `setMode('play')` synchronously; `setMode` sets
`body.dataset.mode` + emits `mode:change` synchronously (app.js:117). No `await`
before return. So exit **must run BEFORE** the tab-switch activation code, in the
same synchronous click handler. Fire-and-forget `refreshAnalysis()` in flight after
is the existing pattern (cf. undo, app.js:539) — not a new risk.

## `registerModeHandlers` (app.js:110)
No shape validation — stores handlers as-is. Adding `isDirty` is clean/additive:
touch each module's registration + the new seam's `h.isDirty ? h.isDirty() : false`.

## Invariant risks flagged
- **api-only boundary**: new seam must live on `api.hub` (like `ensurePlay`); no
  cross-module import of app.js.
- **Never bypass `setMode`** / never hand-roll mode flip — route through registered `exit`.
- **Blunder flush** is the top correctness risk — must go through `exitTrainer`.
- **Setup silent loss** is the top UX-regression risk — no dirty signal exists.
- **Review ownership**: exitReview sits in the hub, not review.js, and isn't
  registered — the structural asymmetry to resolve.
