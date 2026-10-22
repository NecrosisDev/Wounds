"""Write the wound-skin bake shaders (vertex, empty prelude, fragment) for glslcheck.
Usage: python extract_bake.py <wounds_bake.inl> <out dir>"""
import re
import sys

s = open(sys.argv[1], encoding="utf-8").read().replace("\r\n", "\n")


def raw(name):
    m = re.search(r"static const char\* const " + name + r' = R"glsl\((.*?)\)glsl";', s, re.S)
    return m.group(1)


d = sys.argv[2]
open(d + "/bv.glsl", "w").write(raw("woundSkinVertex"))
open(d + "/bp.glsl", "w").write("")
open(d + "/bf.glsl", "w").write(raw("woundSkinFragment"))
