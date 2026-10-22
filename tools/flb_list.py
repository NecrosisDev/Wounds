"""Read-only: shader members (Resource.rpk shading.flb etc.) and skin/undead-looking texture or
model names across the game's archives. Prints names and uniform lists only, never shader source.
Usage: python -I flb_list.py <tools/exanimate> <game>"""
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from exanimate import flb, rpk  # noqa: E402

game = Path(sys.argv[2])
WORDS = ("skin", "undead", "decay", "rot", "corpse", "flesh", "zomb", "mummy", "blood", "wound", "gore", "skel")
for archive in sorted(game.glob("*.rpk")):
    found = rpk.members(archive)
    names = [m.path for m in found if any(w in m.path.lower() for w in WORDS)]
    if names:
        print(archive.name, len(names), names[:40])
res = game / "Resource.rpk"
for m in rpk.members(res):
    if ".flb/" not in m.path:
        continue
    with res.open("rb") as f:
        f.seek(m.offset)
        text = flb.decode(f.read(m.size))
    low = text.lower()
    hits = [w for w in WORDS + ("decay", "age", "wet", "dirt") if w in low]
    if hits:
        print(m.path, hits, [u[1] for u in flb.uniforms(text)][:16])
