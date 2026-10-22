"""Read-only: every textures.flb / shading.flb member name with its uniform names (no source).
Usage: python -I flb_names.py <tools/exanimate> <game> [filter]"""
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from exanimate import flb, rpk  # noqa: E402

res = Path(sys.argv[2]) / "Resource.rpk"
want = sys.argv[3].lower() if len(sys.argv) > 3 else ""
names = []
for m in rpk.members(res):
    if ".flb/" not in m.path:
        continue
    names.append(m.path)
    if want and want not in m.path.lower():
        continue
    with res.open("rb") as f:
        f.seek(m.offset)
        text = flb.decode(f.read(m.size))
    print(m.path, len(text), [u[1] for u in flb.uniforms(text)])
if not want:
    print(" ".join(n.split("/", 1)[1] for n in names))
