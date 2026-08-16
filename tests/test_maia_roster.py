"""M6 roster tests — maiaBand net wiring, policy sharpness, and the
error-injection layer on the Maia path. Engine-free (fakes only).

Seams: ``main.maia_ready_for`` / ``main.get_maia_engine`` are bare-name
imports patched on ``main`` (the spec-pinned targets); the bot engine is a
recording fake passed straight to ``select_persona_move``.
"""

from __future__ import annotations

import asyncio

import pytest

from app import maia_engine, main, personas
from app.maia_engine import pick_from_priors, policy_sharpness

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# A QUEENLESS middlegame (material 44 < 56 → game_phase "middlegame", so the
# phase gate is open) where White's d4 knight hangs to Nc6 — opponent_threat
# sees a real threat for the blunder gate. The gates are phase-gated: an
# opening-phase FEN would silently never fire either tier.
HANGING = "r1b1kb1r/ppp1pppp/2n2n2/3p4/3N4/2N5/PPPPPPPP/R1B1KB1R w KQkq - 0 8"


# --------------------------------------------------------------------------- #
# policy_sharpness
# --------------------------------------------------------------------------- #


def test_policy_sharpness_pivot_and_direction():
    assert policy_sharpness(120) == pytest.approx(1.0)
    assert policy_sharpness(80) == pytest.approx(1.5)   # cool → sharper
    assert policy_sharpness(200) == pytest.approx(0.6)  # hot → flatter


def test_policy_sharpness_clamped():
    assert policy_sharpness(10) == 2.5    # 120/10 = 12 → cap
    assert policy_sharpness(10_000) == 0.5  # → floor


def test_policy_sharpness_garbage_degrades_to_neutral():
    assert policy_sharpness(0) == 1.0
    assert policy_sharpness(-5) == 1.0
    assert policy_sharpness(float("nan")) == 1.0
    assert policy_sharpness("x") == 1.0


# --------------------------------------------------------------------------- #
# pick_from_priors sharpness
# --------------------------------------------------------------------------- #

PRIORS = [
    {"uci": "e2e4", "p": 0.45},
    {"uci": "d2d4", "p": 0.30},
    {"uci": "g1f3", "p": 0.15},
    {"uci": "b1c3", "p": 0.05},
]


def test_default_sharpness_is_m2_identical():
    # Omitting sharpness must reproduce the M2 draw exactly, seed for seed.
    for s in range(50):
        assert pick_from_priors(PRIORS, s) == pick_from_priors(PRIORS, s, 1.0)


def test_sharp_exponent_concentrates_flat_spreads():
    n = 600

    def top_share(sharpness):
        picks = [pick_from_priors(PRIORS, s, sharpness) for s in range(n)]
        return picks.count("e2e4") / n

    assert top_share(2.5) > top_share(1.0) > top_share(0.5)


def test_flat_exponent_never_resurrects_sub_cutoff_howler():
    # 0.01 < MAIA_MIN_PRIOR: excluded from the pool no matter how flat the
    # exponent makes the weights (eligibility uses RAW p).
    priors = PRIORS + [{"uci": "a2a3", "p": 0.01}]
    picks = {pick_from_priors(priors, s, 0.5) for s in range(400)}
    assert "a2a3" not in picks


# --------------------------------------------------------------------------- #
# maiaBand → net path
# --------------------------------------------------------------------------- #


def test_maia_band_persona_ready_when_band_net_present(monkeypatch, tmp_path):
    (tmp_path / "maia-1100.pb.gz").write_bytes(b"stub")
    monkeypatch.setenv("MAIA_WEIGHTS_DIR", str(tmp_path))
    monkeypatch.setattr(maia_engine.shutil, "which", lambda _: "/usr/bin/lc0")
    assert maia_engine.maia_ready_for("teddy") is True   # band 1100
    assert maia_engine.maia_ready_for("grant") is False  # band 1800 net absent
    assert maia_engine.maia_ready_for("vera") is False   # no band, not in MAIA_NETS


def test_every_maia_persona_resolves_its_own_band_net(monkeypatch, tmp_path):
    # With all nine published nets present, every maiaBand persona is ready
    # and resolves to exactly maia-<its band>.pb.gz (catalog/net coherence —
    # a wrong intermediate band cannot hide behind a spot check).
    for band in range(1100, 2000, 100):
        (tmp_path / f"maia-{band}.pb.gz").write_bytes(b"stub")
    monkeypatch.setenv("MAIA_WEIGHTS_DIR", str(tmp_path))
    monkeypatch.setattr(maia_engine.shutil, "which", lambda _: "/usr/bin/lc0")
    maia = [p for p in personas.all() if p.maiaBand is not None]
    assert len(maia) == 12
    for p in maia:
        assert maia_engine.maia_ready_for(p.id) is True
        assert maia_engine._net_path_for(p.id) == tmp_path / f"maia-{p.maiaBand}.pb.gz"


def test_legacy_map_still_wins_for_casey(monkeypatch, tmp_path):
    (tmp_path / "maia-1400.pb.gz").write_bytes(b"stub")
    monkeypatch.setenv("MAIA_WEIGHTS_DIR", str(tmp_path))
    monkeypatch.setattr(maia_engine.shutil, "which", lambda _: "/usr/bin/lc0")
    assert maia_engine.maia_ready_for("casey") is True


# --------------------------------------------------------------------------- #
# select_persona_move — injection on the Maia path
# --------------------------------------------------------------------------- #


class FakeMaia:
    """Returns a fixed argmax with a single dominant prior (sampling is then
    deterministic: the argmax)."""

    def __init__(self, uci="e2e4"):
        self.uci = uci

    async def top_move(self, fen, persona_id):
        return {"uci": self.uci, "san": "e4", "priors": [{"uci": self.uci, "p": 0.97}]}


class RecordingBot:
    """Bot-engine fake: serves scripted candidates and records (k, elo)."""

    def __init__(self, cands):
        self.cands = cands
        self.calls = []

    async def candidates(self, fen, k=1, elo=None):
        self.calls.append({"fen": fen, "k": k, "elo": elo})
        return self.cands[:k]


def _persona(pid):
    p = personas.get(pid)
    assert p is not None
    return p


def _wire_maia(monkeypatch, maia, ready_ids):
    monkeypatch.setattr(main, "maia_ready_for", lambda pid: pid in ready_ids)
    monkeypatch.setattr(main, "get_maia_engine", lambda: maia)


def test_zero_dial_maia_persona_never_calls_sf(monkeypatch):
    # grant (1800): dials all zero → pure Maia; the bot engine must not be hit.
    bot = RecordingBot([])
    _wire_maia(monkeypatch, FakeMaia(), {"grant"})
    out = asyncio.run(
        main.select_persona_move(bot, _persona("grant"), START, 20, 1, [])
    )
    assert out == {"uci": "e2e4", "engine": "maia"}
    assert bot.calls == []


def test_injection_uses_clamped_sf_elo(monkeypatch):
    # teddy (display 800, blunderRate .45 / mistakeRate .5): across many seeds
    # some ply fires a gate; every SF call must carry the clamped 1320 —
    # never the display 800.
    cands = [
        {"uci": "d4f5", "san": "Nf5", "scoreCp": 30},
        {"uci": "e2e3", "san": "e3", "scoreCp": -80},
        {"uci": "a2a3", "san": "a3", "scoreCp": -140},
        {"uci": "h2h4", "san": "h4", "scoreCp": -200},
        {"uci": "f2f3", "san": "f3", "scoreCp": -300},
    ]
    bot = RecordingBot(cands)
    _wire_maia(monkeypatch, FakeMaia("d4f5"), {"teddy"})
    for seed in range(40):
        asyncio.run(
            main.select_persona_move(bot, _persona("teddy"), HANGING, 30, seed, [])
        )
    assert bot.calls, "expected at least one injected ply across 40 seeds"
    assert all(c["elo"] == 1320 for c in bot.calls)


def test_injected_move_keeps_engine_maia(monkeypatch):
    # Force the mistake tier to fire (mistakeRate=1.0 persona clone) and give
    # candidates with a clean in-band option; the reply must still say maia.
    teddy = _persona("teddy")
    forced = personas.Persona(
        id=teddy.id, name=teddy.name, elo=teddy.elo, style=teddy.style,
        description=teddy.description, temperature=teddy.temperature,
        blunderRate=0.0, threatDistance=teddy.threatDistance,
        mistakeRate=1.0, maiaBand=teddy.maiaBand,
    )
    cands = [
        {"uci": "d4f5", "san": "Nf5", "scoreCp": 40},
        {"uci": "e2e3", "san": "e3", "scoreCp": -60},   # 100cp loss → in band
        {"uci": "a2a3", "san": "a3", "scoreCp": -80},   # 120cp loss → in band
    ]
    bot = RecordingBot(cands)
    _wire_maia(monkeypatch, FakeMaia("d4f5"), {"teddy"})
    seen = set()
    for seed in range(30):
        out = asyncio.run(
            main.select_persona_move(bot, forced, HANGING, 30, seed, [])
        )
        assert out["engine"] == "maia"
        seen.add(out["uci"])
    # The mistake tier actually swapped some plies off the Maia argmax.
    assert seen - {"d4f5"}, "expected injected mistakes across 30 seeds"


def test_injection_failure_soft_keeps_maia_move(monkeypatch):
    class DeadBot:
        async def candidates(self, fen, k=1, elo=None):
            raise main.BotEngineUnavailable("no binary")

    teddy = _persona("teddy")
    _wire_maia(monkeypatch, FakeMaia(), {"teddy"})
    out = asyncio.run(
        main.select_persona_move(DeadBot(), teddy, HANGING, 30, 3, [])
    )
    assert out == {"uci": "e2e4", "engine": "maia"}


def test_sf_fallback_clamps_display_elo(monkeypatch):
    # Maia not ready → teddy falls back to the SF pipeline; candidates must
    # see 1320, never 800.
    monkeypatch.setattr(main, "maia_ready_for", lambda pid: False)
    cands = [{"uci": "e2e4", "san": "e4", "scoreCp": 30}]
    bot = RecordingBot(cands)
    out = asyncio.run(
        main.select_persona_move(bot, _persona("teddy"), START, 40, 5, [])
    )
    assert out == {"uci": "e2e4", "engine": "stockfish"}
    assert bot.calls and all(c["elo"] == 1320 for c in bot.calls)


def test_legacy_casey_maia_path_unchanged(monkeypatch):
    # casey has no maiaBand: no sharpness reinterpretation, no injection —
    # the M1/M2 pure-sample semantics (bot engine untouched on the Maia path).
    bot = RecordingBot([])
    _wire_maia(monkeypatch, FakeMaia(), {"casey"})
    out = asyncio.run(
        main.select_persona_move(bot, _persona("casey"), START, 30, 9, [])
    )
    assert out == {"uci": "e2e4", "engine": "maia"}
    assert bot.calls == []
