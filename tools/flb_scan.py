"""Read-only scan of the installed game's shader libraries for skin/decay material shaders.
Prints member names, which of a few words they contain and their uniform names; never prints
shader source. Usage: python -I flb_scan.py <Exanimate tools/exanimate dir> <game dir>"""
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from exanimate import flb, rpk  # noqa: E402

game = Path(sys.argv[2])
WORDS = ("skin", "decay", "rot", "undead", "flesh", "blood", "wound", "corpse", "bone", "mummy", "dirt", "age")
for archive in sorted(game.glob("*.rpk")):
    try:
        found = rpk.members(archive)
    except Exception as e:  # not every rpk need parse
        print("skip", archive.name, e)
        continue
    for m in found:
        if not m.path.lower().endswith(".flb") and ".flb/" not in m.path.lower():
            continue
        with archive.open("rb") as f:
            f.seek(m.offset)
            data = f.read(m.size)
        try:
            text = flb.decode(data)
        except Exception:
            continue
        low = (m.path + "\n" + text).lower()
        hits = [w for w in WORDS if w in low]
        names = m.path.lower()
        if any(w in names for w in ("skin", "decay", "rot", "undead", "flesh", "blood", "corpse", "bone")) or \
                any(w in low for w in ("decay", "undead", "rot ")):
            print(archive.name, m.path, len(text), hits, [u[1] for u in flb.uniforms(text)][:12])
