"""excamera/wounds-06.patch: base-e5/src (a copy of E:\\ExCamera) -> excamera-e5/src, -p0 paths (src/...)."""
import subprocess
from pathlib import Path

here = Path(__file__).resolve().parent.parent
files = ["first_person.cpp", "cue_resources.h", "mod/stone_skin.inl", "mod/headwear_render.inl", "mod/wounds.inl",
         "mod/view_effects.inl", "mod/session.inl"]


def diff(a, b):
    r = subprocess.run(["git", "diff", "--no-index", "--src-prefix=", "--dst-prefix=", "--", a, b], cwd=here, capture_output=True)
    return r.stdout.decode("utf-8")


out = ""
for f in files:
    out += diff(f"base-e5/src/{f}", f"excamera-e5/src/{f}").replace(f"base-e5/src/{f}", f"src/{f}").replace(
        f"excamera-e5/src/{f}", f"src/{f}")
new = diff("/dev/null", "excamera-e5/src/mod/wounds_bake.inl").replace("excamera-e5/src/mod/wounds_bake.inl", "src/mod/wounds_bake.inl")
out += new.replace("diff --git /dev/null src/mod/wounds_bake.inl", "diff --git src/mod/wounds_bake.inl src/mod/wounds_bake.inl")
(here / "excamera" / "wounds-06.patch").write_bytes(out.encode("utf-8"))
print(len(out), "chars")
