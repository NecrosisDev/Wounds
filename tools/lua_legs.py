"""Injuries: legs can be severed too (at the hip or knee), and a character missing a leg stays on the ground
(requested characters.keep_down). Arms keep dropping what the hand holds; legs drop nothing."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent


def sub(rel, old, new):
    p = root / rel
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (rel, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8")


sub("scripts/injuries.lua", """    [15] = {part = 15, bit = 6, side = "left"},  [16] = {part = 16, bit = 7, side = "left"},  [18] = {part = 16, bit = 7, side = "left"},
}""", """    [15] = {part = 15, bit = 6, side = "left"},  [16] = {part = 16, bit = 7, side = "left"},  [18] = {part = 16, bit = 7, side = "left"},
    -- Legs: at the hip (thigh) or the knee (shin, foot); a character missing one stays down.
    [2] = {part = 2, bit = 0, leg = true}, [3] = {part = 3, bit = 1, leg = true}, [4] = {part = 3, bit = 1, leg = true},
    [5] = {part = 5, bit = 2, leg = true}, [6] = {part = 6, bit = 3, leg = true}, [7] = {part = 6, bit = 3, leg = true},
}""")
M = "scripts/main.lua"
sub(M, """    local cut = injuries.SEVER[hit_part]
    if not cut or not cfg.sever then return false end""", """    local cut = injuries.SEVER[hit_part]
    if not cut or not cfg.sever then return false end
    -- A leg only where the character can be kept on the ground afterwards (requested keep_down).
    local keep_down = api.has_capability("characters.keep_down") and characters.keep_down
    if cut.leg and not keep_down then return false end""")
sub(M, """    if api.has_capability("characters.drop_held") and characters.drop_held then
        pcall(characters.drop_held, runtime_target(target), cut.side)
    end
    stump_bleed[target] = cfg.sever_bleed""", """    if cut.side and api.has_capability("characters.drop_held") and characters.drop_held then
        pcall(characters.drop_held, runtime_target(target), cut.side)
    end
    if cut.leg then pcall(characters.keep_down, runtime_target(target), true) end
    stump_bleed[target] = cfg.sever_bleed""")
sub("scripts/main.lua", """     help = "A hard cut can take an arm off at the shoulder or elbow (needs the runtime's joint cut)"},""",
    """     help = "A hard cut can take an arm or leg off; without a leg a character stays on the ground (needs the runtime)"},""")
sub("scripts/main.lua", """format = "percent", help = "Edge damage to an arm in one hit, as % of health, that takes it off"},""",
    """format = "percent", help = "Edge damage to an arm or leg in one hit, as % of health, that takes it off"},""")
sub("manifest.toml", """            "characters.drop_held", "characters.soil_worn", "characters.sever"]""",
    """            "characters.drop_held", "characters.soil_worn", "characters.sever", "characters.keep_down"]""")
print("ok")
