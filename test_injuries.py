"""Load check: builds a stock Lua 5.4 from the runtime's vendored source
(E:\\ExanimaLua\\vendor\\lua) into TEMP once, then runs tests/harness.lua
against scripts/main.lua with a stubbed API (Injuries addon). This checks the addon's own logic
only, not the runtime or the game."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LUA_SRC = Path(os.environ.get('EXANIMA_LUA_SRC', r'E:\ExanimaLua\vendor\lua'))


def lua_exe() -> Path:
    out = Path(tempfile.gettempdir()) / 'injuries-lua'
    exe = out / 'lua.exe'
    if exe.exists():
        return exe
    out.mkdir(exist_ok=True)
    vswhere = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    vs = subprocess.check_output([str(vswhere), '-latest', '-products', '*', '-requires',
                                  'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
    vcvars = Path(vs) / 'VC/Auxiliary/Build/vcvars64.bat'
    cmd = f'call "{vcvars}" >nul && cl /nologo /O2 /MT /DMAKE_LUA /I"{LUA_SRC}" "{LUA_SRC / "onelua.c"}" /Fe:lua.exe'
    subprocess.run(cmd, shell=True, cwd=out, check=True)
    return exe


def main() -> int:
    return subprocess.run([str(lua_exe()), str(HERE / 'tests' / 'harness.lua'), str(HERE)]).returncode


if __name__ == '__main__':
    sys.exit(main())
