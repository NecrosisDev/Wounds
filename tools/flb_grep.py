"""Read-only: print lines of decoded shader members matching a pattern (for private analysis; never
copied into docs). Usage: python -I flb_grep.py <tools/exanimate> <game> <member substring> <regex>"""
import re
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from exanimate import flb, rpk  # noqa: E402

res = Path(sys.argv[2]) / "Resource.rpk"
for m in rpk.members(res):
    if ".flb/" not in m.path or sys.argv[3] not in m.path:
        continue
    with res.open("rb") as f:
        f.seek(m.offset)
        text = flb.decode(f.read(m.size))
    for i, line in enumerate(text.splitlines()):
        if re.search(sys.argv[4], line):
            print(m.path, i, line.strip()[:160])
