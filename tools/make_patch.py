"""Write excamera/wounds-01.patch: the work copy against the base copy, -p0 paths (src/...)."""
import subprocess
from pathlib import Path

here = Path(__file__).resolve().parent.parent
files = ["src/first_person.cpp", "src/mod/overlay.inl", "src/mod/view_effects.inl", "src/mod/session.inl",
         "src/settings_model.h", "src/settings_presentation.cpp", "src/mod/settings.inl"]
out = b""
for f in files:
    r = subprocess.run(["git", "diff", "--no-index", "--src-prefix=", "--dst-prefix=", "--", f, "../excamera-work/" + f],
                       cwd=here / "excamera-base", capture_output=True)
    out += r.stdout.replace(b"../excamera-work/", b"")
r = subprocess.run(["git", "diff", "--no-index", "--src-prefix=", "--dst-prefix=", "--", "/dev/null",
                    "../excamera-work/src/mod/wounds.inl"], cwd=here / "excamera-base", capture_output=True)
new = r.stdout.replace(b"../excamera-work/", b"")
new = new.replace(b"diff --git /dev/null src/mod/wounds.inl", b"diff --git src/mod/wounds.inl src/mod/wounds.inl")
(here / "excamera" / "wounds-01.patch").write_bytes(out + new)
print(len(out + new), "bytes")
