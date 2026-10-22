"""Offline checks for Ground Fighters: rebuilds clips.bin (with its own splice and parse check), splices
the installed humanoid.rsq in Python into TEMP, then runs tests/harness.lua (stock Lua 5.4) to check the
Lua splice gives the same bytes and the addon's logic against a stubbed runtime. Not the runtime or the game.
    python -X utf8 -B test_crawlers.py [--game <Exanima folder>] [--tools <Exanimate tools/exanimate>]"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LUA = Path(tempfile.gettempdir()) / "injuries-lua" / "lua.exe"  # built by E:\Wounds\test_injuries.py


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", type=Path, default=Path(r"D:\SteamLibrary\steamapps\common\Exanima"))
    ap.add_argument("--tools", type=Path, default=Path(r"C:\Users\hunte\Documents\ChatGPT\Exanimate\tools\exanimate"))
    a = ap.parse_args()
    clips = HERE / "scripts" / "clips.bin"
    subprocess.run([sys.executable, "-I", "-X", "utf8", "-B", str(HERE / "tools" / "make_clips.py"), str(a.tools), str(a.game),
                    str(clips), "--check"], check=True)
    sys.path.insert(0, str(a.tools))
    sys.path.insert(0, str(HERE / "tools"))
    from exanimate import rpk  # noqa: E402
    import splice  # noqa: E402
    tmp = Path(tempfile.gettempdir()) / "ground-fighters"
    tmp.mkdir(exist_ok=True)
    installed = rpk.read(a.game / "Resource.rpk", "humanoid.rsq")
    (tmp / "humanoid.rsq").write_bytes(installed)
    (tmp / "expected.rsq").write_bytes(splice.splice(installed, clips.read_bytes()))
    if not LUA.exists():
        print("stock lua missing: run E:\\Wounds\\test_injuries.py once")
        return 2
    return subprocess.run([str(LUA), str(HERE / "tests" / "harness.lua"), str(HERE), str(tmp / "humanoid.rsq"),
                           str(tmp / "expected.rsq")]).returncode


if __name__ == "__main__":
    sys.exit(main())
