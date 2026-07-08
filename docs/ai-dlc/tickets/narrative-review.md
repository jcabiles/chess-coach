# Tickets — narrative-review ("Game commentary")

Spec: `docs/ai-dlc/specs/narrative-review.md` · Contracts:
`docs/ai-dlc/contracts/narrative-review.md` · Branch: `feat/narrative-review`

DAG: T1 ∥ T2 (disjoint files) → T3 (needs both) → T5. T4 (frontend-only) can run
parallel with T3 against the spec's API contract; integration proven in T5.
Max 2 lanes at once: {T1+T2} then {T3, T4} then T5.

## T1 — pure moments extractor (`app/moments.py`)
New engine-free, network-free, SQLite-free module: `extract_moments(plies, leaks,
pos_by_epd, my_color, profile_context) -> payload` per spec — user leaks passthrough,
opponent mistakes via `analysis.win_prob_white` + `analysis.leak_severity` (re-exported
by review.py, defined in analysis.py — do not duplicate thresholds), tide turns
(0.5 crossing, swing ≥ 0.20), `narrow_choice` (pv2 gap ≥ 0.15 in win-prob space; NOT
single-legal-move semantics), missed capitalization, time-trouble flag, cap 12 with
priority + dropped-count note, last-ply no-swing fallback, `lead_in_ply < ply - 1`
relative guard, cp deltas < 60 never emitted.
- Owned files: `app/moments.py`, `tests/test_moments.py`
- Acceptance: POV correctness proven in tests (White-POV eval vs mover-POV win_prob vs
  user-POV leaks); mate-ply NULL-cp handling; empty/short ply lists return empty
  moments without raising; deterministic output ordering.
- Done-condition: `.venv/bin/python -m pytest -q tests/test_moments.py` green offline;
  `ruff check app tests` clean.

## T2 — storage: schema v3 + narrative helpers + invalidation
`_SCHEMA_VERSION` 2→3; migration creates `narratives` table (FK ON DELETE CASCADE);
helpers `get_narrative` / `upsert_narrative` / `delete_narrative` /
`get_pos_cache_many(epd_keys)` (DEPTH-AGNOSTIC — deepest row per EPD); `set_my_color`
and `retag_colors_by_aliases` also delete the narrative row when they reset
analysis_status.
- Owned files: `app/storage.py`, `tests/test_storage_narrative.py` (new)
- Acceptance: migration test upgrades an existing v2 DB file AND fresh-DB path; cascade
  on game delete; invalidation on set_my_color/retag proven; `explanation_json`
  untouched.
- Done-condition: full `.venv/bin/python -m pytest -q` green offline.

## T3 — narrative module + API routes (depends T1 + T2)
`app/narrative.py`: `build_prompt` (pure; facts-only system rules, strict JSON contract),
`generate` (lazy `import anthropic`; `NARRATIVE_MODEL` default `claude-sonnet-5`;
`NARRATIVE_TIMEOUT_S` default 60; max_tokens ≤ 2000; parse+validate, one retry, then
`NarrativeUnavailable`), `is_enabled`, in-flight dict with try/finally + test teardown
fixture. Routes in `app/main.py`: GET/POST `/api/games/{id}/narrative` per spec —
payload from `storage.get_plies` + `get_leaks` + `accuracy.summarize` + profile
clusters; EPDs from stored `fen_before` (no PGN replay); staleness fingerprint
re-checked before upsert; error codes 409/422/503/502; analyze route deletes cached
narrative before re-analysis. `app/models.py`: `NarrativeData`,
`NarrativeStatusResponse`.
- Owned files: `app/narrative.py`, `app/main.py` (HOTSPOT — single owner),
  `app/models.py` (HOTSPOT), `tests/test_narrative_api.py` (new),
  `tests/conftest.py` (teardown fixture only)
- Acceptance: fake-generator tests cover no-key 503 + enabled:false, not-analyzed 409,
  <4 plies 422, success caches + GET round-trip, concurrent POST 409, staleness discard,
  re-analyze deletes cache; NO network/anthropic import in default test run.
- Done-condition: full `.venv/bin/python -m pytest -q` green offline, within ~35 s
  baseline; ruff clean.

## T4 — frontend: narrative panel + moment cards (parallel with T3)
`static/review.js`: GET narrative in `loadReviewData`; collapsible `#review-narrative`
panel under summary strip (Generate button / disabled-hint / spinner / Regenerate /
read-more toggle); moment cards on `review:ply` in foresight host area
(`review-moment-card` class); clear narrative state in `openGame`; extend `postJSON`/
`fetchJSON` to attach `{status, detail}` to thrown Errors (backward-compatible).
`static/index.html`: host element. `static/review.css`: tokens-only, AA,
:focus-visible.
- Owned files: `static/review.js`, `static/review.css`, `static/index.html`
  (HOTSPOT — single owner; no app.js import, no app.js edits)
- Acceptance: all button states reachable; panel does not collide with the PR #35
  analyzing-note (which renders into `#review-game-summary`); no console errors.
- Done-condition: exercised in browser (Playwright MCP or manual) against a live
  server with a stubbed/fake backend response if T3 not merged yet.

## T5 — deps, docs, end-to-end verify (barrier: after T1–T4)
Add `anthropic>=0.40` to `requirements.txt` (user installs in own terminal — sandbox
blocks pip; SETUP-SANDBOX.md convention); README game-review section gains a short
"AI game commentary" paragraph + env vars (`ANTHROPIC_API_KEY`, `NARRATIVE_MODEL`,
`NARRATIVE_TIMEOUT_S`); full Verify-by from spec: offline pytest + ruff, then live
browser walkthrough WITH real key (generate → cached reload → Regenerate → retag
invalidates → no-key disabled state); no debug artifacts; PR opened.
- Owned files: `requirements.txt`, `README.md`, `SETUP-SANDBOX.md`
- Acceptance: spec Verify-by checklist all green, evidence in PR description.
- Done-condition: PR opened from `feat/narrative-review` with evidence pasted.
