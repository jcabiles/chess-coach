# Spec — Repertoire Trainer (tree + jump + practice)

**Goal (one line):** A curated, collapsible **repertoire tree** you click to **jump**
straight to a common position (full move history intact), plus a first-cut **practice
mode** where the app plays the opponent from your prepared lines — random among your
prepared replies, take-back/reveal on your deviations, and a hand-off to Stockfish once
prep is exhausted.

Status: inception (plan gate). No feature code until approved.

---

## Why

Playing every opening move one drag at a time to reach a position you study constantly
is tedious. The user always follows a fixed repertoire (1.e4 as White — Italian vs ...e5,
Open Sicilian vs ...c5, Scandinavian vs ...d5; as Black — Sicilian vs 1.e4, Indian vs
1.d4) plus the trap lines already built. This feature turns that repertoire into a
navigable tree: one click to land in a position, and a practice mode to rehearse the
lines against an opponent that follows the prep (not the engine — until prep ends).

This is also a **foundation**: the same line data drives both the jump and the practice
opponent, so future work (quiz/spaced-repetition, notes) hangs off one model.

---

## Decisions (locked via interview 2026-06-28)

1. **Shape** = a **drill-down repertoire tree**, grouped **As White / As Black** →
   opening → variation/line (leaf). Curated content (~8–15 lines), authored by us and
   approved by the user; **trap lines appear as leaves** under their parent opening.
2. **Jump** = **full move history**. Clicking a leaf/line sets `baseFen = START`,
   `moves = <line UCIs>`, `cursor = moves.length`: you can Undo back through the line, the
   opening auto-names, the Book Move badge works, and you continue playing. (Not a raw
   FEN load.)
3. **Practice mode is in scope** (first cut), with these mechanics:
   - **Opponent source while in prep** = a **random** choice among *your prepared replies*
     at the current point (variety across your prep), constrained to the chosen scope.
   - **Your deviation** = **rejected**: the off-line move is taken back, marked off-line,
     with **take-back / reveal** affordances (reuse the trap-practice UX). The engine
     never plays *your* move.
   - **End of prep** = **hand off to Stockfish**: once no prepared continuation remains in
     scope, the app plays the opponent via the engine so you play out the middlegame. This
     is the *only* place the engine plays. (The user's "play, but not the engine" applies
     to the opening prep; after prep the engine is welcome.)
4. **Coverage** = a **curated set** (~8–15 named lines) covering the repertoire above +
   trap lines; the user approves the final list before it lands; every line
   python-chess-verified.

---

## Data model — `data/repertoire.json` (NEW)

A flat list of named lines (easy to author + verify one at a time, like `traps.json`);
the **tree** is *derived at load*, not hand-nested.

```json
{
  "lines": [
    {
      "id": "italian-giuoco-pianissimo",
      "name": "Giuoco Pianissimo",
      "parentOpening": "Italian Game",
      "yourColor": "white",
      "line": ["e4","e5","Nf3","Nc6","Bc4","Bc5","c3","Nf6","d3"],
      "note": "Quiet maneuvering middlegame."        // optional, for display
    }
  ]
}
```

- `line` is authored in **SAN** (human-readable, matches how the lines are reasoned
  about). The loader replays it from the standard start with python-chess, which both
  **validates legality** (illegal SAN ⇒ the line is dropped with a warning, never loaded)
  and derives the **UCI sequence** + per-ply data. `yourColor ∈ {white, black}`.
- **Trap leaves**: reuse trap data — a line may reference a trap by
  `"trapId": "fried-liver-attack"` (+ optional `"variation": 0`, `parentOpening`,
  `yourColor`). **Caveat (refuter):** `traps.iter_mainline_ucis()` **cannot** be filtered
  by id — it returns *all* variations of *all* traps at once (19 traps → 20 lines), and a
  multi-variation trap has no single "the mainline". So the loader resolves a leaf via
  `traps.get(trapId)` and rebuilds the line the way `iter_mainline_ucis` does internally
  (`traps.py:250-272`): convert `leadInSan` SAN→UCI and **prepend** it to the chosen
  `variations[variation].mainLine[].uci` (default variation 0). Add a small accessor
  **`traps.mainline_ucis_for(trap_id, variation=0) -> list[str]`** (owned by `traps.py`)
  so `repertoire.py` never re-implements trap internals. Keeps one owner for trap move data.

### Two derived structures (both built at load, from the same lines)

- **Catalog (for the tree UI):** grouped `color → parentOpening → {id, name, leaf line}`.
  Drives the collapsible browse/jump tree.
- **Move tree (for practice traversal):** a per-color **prefix tree** keyed by the UCI
  sequences. Node = a position reached; edges = prepared moves. Used to (a) randomize the
  opponent among prepared children and (b) check your move against the single prepared
  child.

### Invariant (validated at load, tested)

At any node where **it is your turn** (side-to-move == `yourColor`), there is **exactly
one** prepared child (your one repertoire answer). Opponent-turn nodes may have many
(your prepared replies to each opponent try). A conflict (two lines giving different
*your* moves at the same position) is an **authoring error** — logged **loudly** (name the
dropped line + the position) and the conflicting line dropped, and surfaced by the data
test — so practice deviation-checking is always unambiguous. **Design choice, not an
oversight:** supporting *multiple* authored answers at one node (a main line + a sideline
you also play) is explicitly **deferred**; the single-child rule is a first-cut constraint.

> **Out of scope: transpositions.** The move tree is keyed by move *sequence*, not EPD,
> so reaching a prepared position by a different order is not recognized in practice
> (accepted for the first cut; the jump still works from the canonical order).

---

## Practice traversal model

Practice is entered from a tree node (an opening group, a line, or the whole color
forest). The chosen node defines a **scope** = the set of allowed line ids (its
descendants). Practice then:

1. Starts from the **standard start** (board oriented to `yourColor`); state enters a new
   `'rep-practice'` mode (transient, snapshots the play game like trap modes).
2. **Opponent on move** (side-to-move ≠ yourColor): the app auto-plays a **random** child
   of the current move-tree node that stays within scope. If the opponent is on move
   first (you're Black), it opens the game.
3. **You on move:** your move must equal the single prepared child within scope.
   - Match ⇒ advance; the opponent replies (step 2).
   - Mismatch ⇒ **reject**: take the move back, show "Not a prepared move", offer
     **Take back** (already reverted) and **Reveal move** (plays your prepared move).
4. **No prepared continuation in scope** (leaf reached) ⇒ **engine handoff**: from here
   the app auto-plays the **opponent** with Stockfish's best move (`bestMoveUci`), and you
   keep playing freely. Edge cases: engine **absent** ⇒ stop with "Prep complete — engine
   unavailable"; `bestMoveUci` **null at a terminal position** (no legal moves) ⇒ stop with
   the game result; `bestMoveUci` **null mid-game** (empty PV) ⇒ surface "no engine move"
   and fall back to free play (you may move both sides).
5. **Exit** ("Return to my game") restores the snapshotted play game (like trap modes).

The client walks the move tree by the moves played (no EPD) — consistent with the
identity-server-side contract.

---

## Files / interfaces to touch

- **NEW `data/repertoire.json`** — curated lines (see model). Seeded WITH the user
  (research + approval); every line python-chess-verified.
- **NEW `app/repertoire.py`** — module singleton mirroring `traps.py`:
  - `load(path=None) -> None` / `init(path=None)` — import-safe, reset-first, never raise;
    drop malformed/illegal/conflicting lines with a warning.
  - Validate: required fields; `yourColor` valid; SAN `line` replays legally; the
    your-turn-single-child invariant. Build the **catalog** + **move tree** + UCI lines.
  - `tree() -> dict` — `{ "white": <node>, "black": <node>, "catalog": [...] }`, always
    well-formed; empty when no data. (Node = `{uci, san, ply, yourTurn, leaf, name?,
    children: [...]}`.)
  - `iter_lines() -> list[list[str]]` — every line as a full UCI list from the start
    (incl. trap-referenced lines), to fold into the opening book. Exception-safe.
  - **No engine import. No network.** Trap moves come via `app.traps` accessors (one owner).
- **`app/models.py`** — `Analysis.bestMoveUci: str | None = None` (optional, default
  None; backward-safe). Lets the client auto-play the engine opponent in handoff. (No
  existing field changes; the shared `Analysis` shape only *grows* one optional field.)
- **`app/main.py`**:
  - Lifespan: `repertoire.init(str(REPERTOIRE_FILE))` after `openings`/`traps` init.
    **Book fold (refuter):** `book.init` has only two line-source params — `lines=`
    (FILTERED by `book.json` `firstMoves`) and `trap_ucis=` (gated only by `includeTraps`,
    bypasses `firstMoves`), and both are already occupied (`main.py:76-80`). Repertoire
    lines are full-from-start UCI lines that must bypass the `firstMoves` filter, so fold
    them into the **`trap_ucis`** slot:
    `trap_ucis=list(traps.iter_mainline_ucis()) + list(repertoire.iter_lines())`
    (a future flank repertoire line then isn't silently dropped by
    `firstMoves=['e2e4','d2d4']`). **No `book.py` signature change needed.** Keep it inside
    the existing try/except guard.
  - **NEW route** `GET /api/repertoire` → `{"tree": repertoire.tree()}` (well-formed,
    empty when absent; never 500). Fixed path — no ordering hazard.
  - `_build_analysis`: set `bestMoveUci = result.pv[0].uci() if result.pv else None`.
- **`static/index.html`** — a **"My Repertoire"** panel section (mirror `#traps-section`)
  holding the collapsible tree; a **repertoire-practice bar** in the board column (mirror
  `#trap-bar`): status line, **Take back**, **Reveal move**, **Return to my game**.
- **`static/app.js`** — single owner of the client logic:
  - Fetch `/api/repertoire`; render the collapsible tree (color → opening → line); each
    line offers **Jump** (full-history jump) and its scope offers **Practice**.
  - `'rep-practice'` FSM per the traversal model: gate `onUserMove`; auto-opponent
    (random prepared child, then engine `bestMoveUci` after prep); deviation
    reject + take-back + reveal; exit restores the play snapshot. **Reuse only the UX
    scaffolding** from trap-practice (snapshot the play game, body-class swap, the bar,
    take-back/reveal — `enterTrap`/`applyTrapModeUI` shape). **The trap-practice *move
    engine* is NOT reusable (refuter):** it is script-driven off a precomputed FEN array
    (`buildTrap` → `trap.fens[]`; `applyPracticeStep` ignores the runtime move). Rep-practice
    needs a **new move-application primitive** that plays an *arbitrary runtime UCI* and
    recomputes the position — both the random prepared child and the engine `bestMoveUci`
    are runtime, not scripted. Build it from the existing pure helpers
    (`positionFromFen()` + `pos.play(parseUci(uci))`, as `positionAt`/`onUserMove` already
    do, `app.js:151-160`/`258-301`).
  - **Transience (refuter):** add `'rep-practice'` to the `persist()` early-return guard
    (`app.js:72-73` currently lists only `trap-watch`/`trap-practice`) so a practice session
    is never written to localStorage; confirm `restore()` (`app.js:101+`) never resurrects
    a `rep-practice` mode.
- **`static/style.css`** — tree + practice-bar styles, **tokens only**, mirroring the
  trap/setup bar + traps-section classes; AA contrast in the dark theme.

---

## Out of scope

- **Transposition merging** (tree is move-order-specific).
- **In-app editing** of the repertoire (content is the data file; grow it by editing).
- **Spaced-repetition / progress tracking / quiz scoring** (this lays the foundation only).
- **Engine difficulty tuning** for the handoff opponent (it plays the best move).
- **Persisting** a practice session (transient, like trap modes). *(The `persist()`
  early-return guard for `'rep-practice'` IS in scope — it's the mechanism that makes it
  transient; what's out of scope is *adding* practice-session persistence.)*
- Any change to `/api/load`, `/api/analyze` semantics (beyond the additive
  `bestMoveUci`), trap watch/practice behavior, engine config, or search depth.

---

## Constraints

- **Stateless per request** — jump + practice are client state; `/api/repertoire` is a
  pure read of loaded data.
- **EPD/identity server-side only** — the client walks the move tree by UCI sequence; it
  never computes EPDs. (Server still owns `/api/opening` naming + the book set.)
- **Graceful degrade** — missing/empty `data/repertoire.json` ⇒ `tree()` empty ⇒ the
  "My Repertoire" section simply doesn't render; the rest of the app is unchanged.
- **Engine optional** — practice prep needs **no** engine; only the end-of-prep handoff
  does, and it degrades to "engine unavailable, prep complete" when Stockfish is absent.
- **Backward-safe** — `bestMoveUci` is optional/default-None on `Analysis`; no existing
  field changes type. **Verified (refuter):** the only exact-dict test is `test_api.py:65`
  (`test_move_illegal`), which asserts a `MoveResponse` with `analysis=None` — `bestMoveUci`
  lives *inside* `Analysis`, so that test is **unaffected** (the `book`→`MoveResponse`
  precedent does **not** apply here). The test ticket only **adds** coverage; it does **not**
  edit `test_move_illegal`.
- **One file = one owner** — `static/app.js` is the single hotspot for all client logic.

---

## Verify-by (what `/verify-change` checks)

- **Data `tests/test_repertoire.py`** — against the shipped `data/repertoire.json`: every
  `line` replays legally from the start (python-chess); `yourColor` valid; the
  your-turn-single-child invariant holds for all loaded lines; trap-referenced leaves
  resolve to a real trap mainline; `iter_lines()` returns full UCI lines; a deliberately
  illegal/conflicting fixture line is dropped, not raised.
- **Loader/tree `tests/test_repertoire.py`** (fixture `tests/fixtures/repertoire_sample.json`)
  — `tree()` groups by color → opening → line; the move tree branches at opponent nodes
  and is single-child at your nodes; empty/missing file ⇒ `tree()` is well-formed + empty.
- **API `tests/test_repertoire_api.py`** — `GET /api/repertoire` returns
  `{"tree": {...}}` with the grouped structure; with no data loaded it returns an empty
  well-formed tree (never 500). `Analysis.bestMoveUci` is present (UCI string) on
  `/api/analyze` / `/api/move` via a fake engine, `None` when no PV.
- **Book extension** — a curated line's positions are recognized by `book.is_book_move`
  (so a jumped repertoire position shows the Book Move badge). (Add to the repertoire/book
  data test.)
- **Browser/manual** — tree renders grouped + collapsible; clicking a leaf jumps with
  full history (Undo steps back through the line; opening name + Book Move badge show);
  Practice: opponent auto-replies with a prepared (random, in-scope) move; a non-prepared
  move is rejected with take-back + reveal; reaching prep's end hands off to the engine
  (an opponent move appears from Stockfish); "Return to my game" restores the prior game.
- Full suite stays green (use `pytest --collect-only -q` for the exact baseline rather
  than a guessed count).

---

## Notes on size / staging (for the plan gate)

The client ticket (`static/app.js`) is the largest piece and bundles two separable
milestones: **(A) tree + jump** (the stated MVP) and **(B) the practice FSM + engine
auto-opponent** (the new-in-scope part, and the heaviest new control flow — nothing
auto-plays a move today). Recommend implementing/verifying **A first** (shippable on its
own), then **B**. The ticket keeps a single owner for `app.js`; the two milestones are
called out so review and browser-verification happen in two passes.
