# Finding ledger — movelist relocation spec review (2026-08-13)

**Bottom line:** dual review (Claude refuter + Codex gpt-5.6-sol) both returned
`fail` on the v1 spec; 8 distinct findings after merging overlaps, all accepted and
folded into the spec, none rejected. One accepted finding (tab visibility) carries a
user-facing behavior decision surfaced at Gate 2.

| # | Finding | Source (severity) | Adjudication | Spec fix |
|---|---|---|---|---|
| 1 | `.action-col` is `align-self:start` → `flex:1` list has no height source; overflow clipped by `main{overflow:hidden}`, moves unreachable | refuter (blocker) + Codex MR-002 (major) | **Accepted** — verified `style.css:383-393`, `:294` | Spec now requires `align-self:stretch` + full `min-height:0` flex chain |
| 2 | Relocated list visible on Opening/Traps/Repertoire/Insights tabs (mode stays `play` while tab-browsing; no tab hook on body) | refuter (blocker) | **Accepted with decision** — consistent with always-visible board buttons; documented as intended, user confirms at Gate 2 | Spec documents cross-tab visibility as intended + verify step added |
| 3 | Bot-play mode undefined; stale list (pre-existing gap made prominent by relocation) | Codex MR-001 (major) + refuter (minor) | **Accepted** — verified `movelist.js:78`, `botplay.js` sets mode | Render in `bot-play`; clicks stay no-ops via `goto()` play/review gate |
| 4 | Bot-rail-open 1281–1440px: 300px rail + ~220px column crushes board | Codex MR-003 (major) | **Accepted** — verified grid `style.css:298-303`, `:2225-2239` | Responsive column width + rail-open acceptance case |
| 5 | `offsetTop` example wrong (no positioned ancestor) | refuter (minor) | **Accepted** | Spec prescribes `getBoundingClientRect()` deltas (or `position:relative` on `#move-list`) |
| 6 | ≤820px flex-wrap doesn't guarantee list lands below the button row | refuter (minor) | **Accepted** | `flex-basis:100%` on the block in the media query |
| 7 | Persisted-collapsed card could consume column as blank flex space | Codex MR-004 (minor) | **Accepted** | `.movelist-block.collapsed { flex: 0 0 auto }` + reload test |
| 8 | Shared `.movelist-toggle`/`.movelist-chevron` classes also style Play-vs-Bot + settings disclosures | Codex MR-005 (minor) | **Accepted** | All new rules scoped under `.action-col .movelist-block`; regression check on both other disclosures |

Deterministic baseline: `.venv/bin/python -m pytest -q` → 1022 passed (refuter-run).
Reviewer conflicts: none material (bot-play severity differed; resolutions agreed).
