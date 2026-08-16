"""One-shot: regenerate data/personas.json from personas._DEFAULT_PERSONAS.

Keeps the committed file and the built-in default byte-for-byte in sync
(the test_personas_json_matches_default_personas invariant). ``maiaBand`` is
omitted for SF-backed personas so their entries keep the pre-M6 shape.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.personas import _DEFAULT_PERSONAS  # noqa: E402

entries = []
for p in _DEFAULT_PERSONAS:
    d = p.as_dict()
    if d["maiaBand"] is None:
        del d["maiaBand"]
    entries.append(d)

out = Path(__file__).resolve().parents[1] / "data" / "personas.json"
out.write_text(
    json.dumps({"personas": entries}, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
print(f"wrote {len(entries)} personas -> {out}")
