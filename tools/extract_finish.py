"""Write the finishing program's shader sources (vertex, prelude, body) out of view_effects.inl for glslcheck.
Usage: python extract_finish.py <view_effects.inl> <out dir>"""
import re
import sys

s = open(sys.argv[1], encoding="utf-8").read().replace("\r\n", "\n")


def raw(name):
    head = "static const char* const " + name + " = "
    i = s.index(head) + len(head)
    out = ""
    while True:
        while s[i] in " \n\t":
            i += 1
        if s.startswith("//", i):
            i = s.index("\n", i)
            continue
        if s[i] == ";":
            return out
        if s.startswith('R"glsl(', i):
            j = s.index(')glsl"', i)
            out += s[i + 7:j]
            i = j + 6
            continue
        m = re.match(r"[A-Za-z_]\w*", s[i:])
        if m:
            out += raw(m.group(0))
            i += len(m.group(0))
            continue
        raise SystemExit("unparsed at " + s[i:i + 80])


d = sys.argv[2]
open(d + "/v.glsl", "w").write(raw("viewVertexShader"))
open(d + "/p.glsl", "w").write(raw("viewPrelude"))
open(d + "/b.glsl", "w").write(raw("surfaceShading") + raw("finishShader"))
