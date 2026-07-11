# Contracts — Evaluation on/off toggle

Area: the main **play / Analysis** board's move→eval trigger in `static/app.js`, plus the
Analysis-tab control strip in `static/index.html` / `static/style.css`. Frontend-only — reuses
infra shipped by **analyze-my-color** (`docs/ai-dlc/contracts/analyze-my-color.md`).

## Existing behavioral contracts this change must respect

1. **Two gate functions already decide whether Stockfish runs** (`app.js`):
   - `shouldAnalyzeMove(moverColor)` (line ~74) — gates the `/api/move` `analyze` flag on the
     write path (`onUserMove`, ~475: `doAnalyze = shouldAnalyzeMove(moverColor)`).
   - `shouldAnalyzeCursor(cursor)` (line ~78) — gates the read/nav path (`refreshAnalysis`, ~399:
     `if (!shouldAnalyzeCursor(state.cursor)) { renderSkipped(); … return; }`).
   The on/off master switch must fold into **both**, else one path still calls the engine.

2. **`/api/move { analyze:false }` already exists** (analyze-my-color) → server returns
   `legal:true, analysis:null`, engine NOT called. Eval-off reuses this exact flag; **no backend,
   models, or schema change** is needed.

3. **`renderSkipped()` BLANKS the panel** (`renderSkippedPanel`: eval→`—`, best/PV→`—`,
   `setEvalBar(50)`, "Not evaluated"). analyze-my-color calls it on skipped opponent moves. For
   **eval-off we must NOT call it** — the requirement is to *freeze* the last eval. Freezing =
   skip the refresh / skip re-render entirely, leaving the panel's last-rendered DOM intact.
   This is the key divergence from the analyze-color skip path.

4. **`analysisToken` monotonic guard** (lines 63–66, 389, 402/411, 525): every move bumps the
   token so stale in-flight responses drop. If eval is off we make **no** request, so no token
   concerns on the off path — but on **re-enable** we call `refreshAnalysis()`, which bumps the
   token normally. Safe.

5. **Status line** (`setStatus('Analyzing…')` at ~397/477): must not flash "Analyzing…" when off.
   `onUserMove:477` fires it unconditionally before the `/api/move` await (the write round-trip
   always happens, even `analyze:false`) → must be gated on `evalEnabled` (refuter [med] #3).

5b. **`emit('analysis:start')` at ~396 fires BEFORE the freeze early-out** (refuter [low] #4) —
   so the freeze branch emits `start`+`end` synchronously, same harmless pattern as the existing
   analyze-color skip branch (no `await` between them → the feedback spinner never paints).
   Intentional/inherited, NOT new scope — flagged so a future refactor adding an `await` before
   the early-out doesn't silently introduce a spinner flash.

6b. **`analysisToken` is a supersede signal, not just a nav guard** (refuter [high] #1): toggle-off
   is a NEW supersede event. It must `analysisToken++` (like `onUserMove`/`loadFen`) or an
   in-flight `refreshAnalysis` response will render and un-freeze the panel.

6. **Prefs seam** (`prefs.js`): `readUiPrefs`/`writeUiPref` on `chess-training:ui:v1`. The off
   state is **session-only (reset to on at reload)** per requirements → do NOT persist it here;
   a plain module variable suffices. `analyzeColor` stays persisted and independent.

## Integration points / blast radius
- `onUserMove` (write path), `refreshAnalysis` (read path), `init()` wiring block (~1064, next to
  the `analyze-color` selector wiring).
- Analysis tab markup only (`#tab-analysis`) — trainers, setup, review untouched.
- No shared-state or backend consumers; move-list quality labels for moves made while off are
  simply absent (no analysis ran) — expected.
