# Delta Spec — Evaluation on/off toggle

Contracts: `docs/ai-dlc/contracts/eval-toggle.md`. **Frontend-only** — reuses the
`/api/move analyze=false` path + the two gate functions shipped by *analyze-my-color*.

## Problem (why)
In the Analysis board, every move you play fires a Stockfish eval. On lines the user already
knows (a rehearsed follow-up), that calculation is wasted and adds latency. The user wants to
**suspend evaluation on demand, play the known moves, then re-enable** — without losing their
Evaluate-color choice.

## Goal (one line)
A **one-click toggle button** in the Analysis tab (`Evaluation: On/Off`) that acts as a master
switch over the existing eval gates: when **off**, Stockfish is never called (neither on play nor
on navigation) and the Analysis panel **freezes** its last eval; when flipped back **on**, the
current position is analyzed immediately.

## Locked decisions (from Gate-1 interview)
- **Control:** a dedicated toggle **button** (not a dropdown option), separate from and independent
  of the existing `#analyze-color` selector. On = today's behavior; color filter still applies.
- **Master switch:** a new `evalEnabled` (default `true`) module var in `app.js`. Both
  `shouldAnalyzeMove` and `shouldAnalyzeCursor` return `false` when `evalEnabled` is false —
  regardless of `analyzeColor`.
- **When off = FREEZE, not blank:** on the off path we must **not** call `renderSkipped()` (that
  blanks the panel). Instead skip the request and skip re-rendering the panel — the last-rendered
  eval/quality DOM stays. The button's OFF state is what signals the freeze is intentional.
- **Toggle-off invalidates in-flight requests (refuter [high] #1):** a `refreshAnalysis()` started
  by a nav just before the click is NOT covered by the existing `analysisToken` guard (that guard,
  commit `2dec2cb`, closes a *different* race). On toggle-off we must **`analysisToken++`** —
  exactly as `onUserMove`/`loadFen` do — so any in-flight response drops instead of rendering and
  un-freezing the panel.
- **aria-pressed mapping (refuter [high] #2) — one canonical rule:** `aria-pressed="true"` ⇒ eval
  **ON** (toggle is "pressed"/active), matching `evalEnabled` default `true`. Static markup ships
  `aria-pressed="true"`; the muted/paused style targets `[aria-pressed="false"]` (off).
- **On re-enable:** call `refreshAnalysis()` so the frozen eval catches up to the current cursor.
- **Session-only:** off state is a plain module var, **not persisted**. Reload always returns to
  ON. (`analyzeColor` stays persisted + independent.)
- Play/Analysis board only. `evalEnabled === true` reproduces current behavior bit-for-bit.

## In scope

### `static/app.js`
- New module var: `let evalEnabled = true;` (session-only — no `readUiPrefs`).
- **`shouldAnalyzeMove(moverColor)`** (~74): prepend `if (!evalEnabled) return false;`
- **`shouldAnalyzeCursor(cursor)`** (~78): prepend `if (!evalEnabled) return false;`
- **`refreshAnalysis`** (~399): the existing early-out
  `if (!shouldAnalyzeCursor(state.cursor)) { renderSkipped(); setStatus(''); emit('analysis:end');
  return; }` would BLANK the panel when off. Split the cases so **eval-off freezes** instead:
  - when off (`!evalEnabled`): `setStatus(''); emit('analysis:end'); return;` — **no
    `renderSkipped()`**, panel left frozen.
  - the analyze-color skip (enabled but wrong color) keeps calling `renderSkipped()` unchanged.
  - Implementation guidance: gate on `!evalEnabled` first (freeze branch), then the existing
    `!shouldAnalyzeCursor` branch (skip branch). Keep the check AFTER the in-flight coalesce guard,
    matching analyze-my-color's placement, so the `finally` still resets `analysisInFlight`.
- **`onUserMove`**: three coordinated edits.
  - (~477) The unconditional `setStatus('Analyzing…')` before the `/api/move` await still fires
    when off (the server always validates legality + writes the move, even with `analyze:false`),
    so the status flashes "Analyzing…" though no engine runs (refuter [med] #3). Gate it:
    `if (evalEnabled) setStatus('Analyzing…');` (when off, leave/clear status — no misleading flash).
    Note: analyze-color *skip* (enabled, wrong color) keeps flashing "Analyzing…" as today —
    only the eval-**off** case is suppressed.
  - (~475) `doAnalyze = shouldAnalyzeMove(moverColor)` already returns false when off, so
    `/api/move` is sent `analyze:false` (engine not called) and the write path runs.
  - (~526) the current render branch `if (doAnalyze) applyMoveResponse(data); else
    renderSkipped();` would blank the panel when off. Change to `if (doAnalyze)
    applyMoveResponse(data); else if (evalEnabled) renderSkipped();` (off ⇒ neither → frozen;
    analyze-color skip ⇒ still `renderSkipped()`). Move-list quality label for the ply stays blank
    either way (no analysis) — expected.
- **Toggle wiring** in `init()` (next to the `#analyze-color` block ~1064): reflect initial state
  on the button (`aria-pressed="true"`, label "Evaluation: On"). On click → `evalEnabled =
  !evalEnabled`, update button label + `aria-pressed` per the canonical mapping, then:
  - **now enabled:** call `refreshAnalysis()` (catch up to current cursor).
  - **now disabled:** `analysisToken++` (drop any in-flight `refreshAnalysis` response so it can't
    render and un-freeze the panel — refuter [high] #1). Nothing else; panel is already frozen.

### `static/index.html`
- A `<button id="eval-toggle" type="button" aria-pressed="true">Evaluation: On</button>` in
  `#tab-analysis`, near the `.analyze-color-row` / `#engine-restart-btn`. Ships `aria-pressed="true"`
  because `evalEnabled` defaults `true` (canonical mapping: pressed = on). Label reflects state.

### `static/style.css`
- Style `#eval-toggle` with existing tokens only (no raw hex). On (`[aria-pressed="true"]`) =
  active look; off (`[aria-pressed="false"]`) = muted / paused look. `:focus-visible` ring, AA
  contrast both states.

## Out of scope
- Persisting the off state across reloads (explicitly session-only).
- Any backend / `app/models.py` / `/api/move` change (the `analyze:false` flag already exists).
- Game-review background analysis; opening / traps / repertoire / setup / review modes.
- A keyboard shortcut (considered, deferred — button only for now).
- Retroactively re-analyzing plies played while off (forward-only; blanks stay until revisited).

## Constraints
- `evalEnabled === true` MUST be byte-for-byte today's behavior (regression-safe default).
- Freeze path must NOT call `renderSkipped()` and must NOT flash "Analyzing…".
- Independent of `analyzeColor`: off overrides all colors; color filter unchanged when on.
- Tokens-only CSS, no raw hex, `:focus-visible`, AA contrast; frontend modules never import app.js.
- Pure-module + full pytest suite unaffected (no backend touched); verify in-browser before commit.

## Verify-by
1. **Browser, default (on):** identical to today — moves evaluate, color filter works, `pytest`
   + `ruff` still green (no backend change, but run them).
2. **Toggle off → play a move:** network shows `/api/move { analyze:false }`; panel eval/quality
   **unchanged from before the move** (frozen, not blanked to "—"); status does NOT flash
   "Analyzing…"; button reads "Evaluation: Off" with `aria-pressed="false"`; 0 console errors.
3. **Navigate (undo/redo/move-list) while off:** no `/api/analyze` call; panel stays frozen.
4. **Toggle off mid-navigation (race — refuter [high] #1):** trigger a nav that starts an
   `/api/analyze`, then immediately toggle off before it returns → when the response lands the
   panel does **not** change (frozen); confirm via a slow/deep position or throttled network.
5. **Toggle back on:** current position is analyzed immediately (eval catches up), button reads
   "Evaluation: On" `aria-pressed="true"`; subsequent moves evaluate; color filter still respected.
6. **Reload while off:** returns to ON (session-only).
7. **A11y:** `:focus-visible` ring on the button; `aria-pressed` reflects state per the canonical
   mapping (true=on); AA contrast in both states.
