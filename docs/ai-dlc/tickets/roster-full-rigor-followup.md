# Ticket — bring the 800–1800 roster up to full roadmap rigor

**Bottom line:** the 12-bot Maia roster
([spec](../specs/roster-800-1800.md)) shipped at the pragmatic verification
tier: pytest + an adjacent-rung monotonic ladder probe. This ticket is the
owner-requested follow-up (2026-08-15 interview) that closes the gap to the
roadmap's full M3/M4/M5 acceptance rigor. A future agent should treat the
items below as the acceptance checklist.

## What "full rigor" means here (from roadmap Chapter 4 + specs)

1. **Populate the M3 realism data sets** (blocked on network — sandbox
   cannot reach lichess; the USER must run the fetch):
   - Run `tools/fetch_lichess_sample.py` against ONE recent lichess monthly
     dump (streamed, never fully downloaded) to produce
     `data/realism/dev-<band>.jsonl` (200/band), `eval-<band>.jsonl`
     (500/band) and `EVAL_SHA256`. Bands: 1300–1500 … 1900–2100 exist; the
     new roster ALSO needs sub-1300 bands (800–1000, 1000–1200, 1100–1300)
     — extend `BANDS` in `tools/fetch_lichess_sample.py` first, keeping the
     ECO-disjoint dev/eval split and per-game caps (spec
     [realism-audit](../specs/realism-audit.md), review folds 1/6/8).
2. **Sealed-eval realism report per new persona**
   (`tools/realism_audit.py --set eval`): human-move-match %, blunder/
   mistake frequency vs dials, engine-signature flags, all with Wilson CIs;
   committed as `docs/analytics/realism-baseline.md` (or a successor doc)
   with binary versions + eval-set hash in the header. The sealed set is
   NEVER used for tuning — tune on dev only.
3. **±150 effective-Elo calibration for the 800/1000 rungs** (roadmap M5):
   ≥30 games per probe persona against SF UCI_Elo ladder anchors; measured
   effective Elo within ±150 of the label, reported WITH its confidence
   interval, paired with a maia-1100 blunder-profile comparison; both
   labeled as estimates. Method: honest-bot-rating-assignment research doc
   (`docs/design/research/rating-calibration/`), Option C.
4. **Scale up the ladder probe**: `tools/ladder_probe.py` at ≥50
   color-balanced games per adjacent pair (the shipped run is 24/pair);
   relative-Elo spacing check (rating gaps ≈ 200 ± noise, flag compressed
   rungs); adjust injection dials on DEV evidence only and re-run.
5. **User playtest sign-off** per roadmap: at least one game against each
   new rung, roster "feels varied" confirmation.

## Constraints that still bind

- Engine access only through `app.bot_engine` / `app.maia_engine` for move
  generation; `app.engine.StockfishEngine` allowed as the OFFLINE oracle.
- Suite stays green with no binaries; pure modules stay engine-free.
- Persona ids are frozen (localStorage/PGN keys); dial changes are data-only.
- Tuning never touches the sealed eval set; the harness warns on
  `--set eval` runs.

## Done when

All five items above are complete, numbers are committed under
`docs/analytics/`, dials (if changed) are re-verified by the monotonicity
tests + probe, and the roadmap M5/M6 checkboxes can be honestly ticked.
