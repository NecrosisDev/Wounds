"""Harness: the "injuries.broken" mark and drop_held checks."""
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "tests" / "harness.lua"
t = p.read_text(encoding="utf-8")


def sub(old, new):
    global t
    assert t.count(old) == 1, old[:60]
    t = t.replace(old, new)


sub("""        assert(name == "injuries.mend" and value >= 0 and value <= 255)
        if type(target) == "table" then target = "h" .. target.handle end
        s.marks[target] = value ~= 0 and value or nil""", """        assert((name == "injuries.mend" or name == "injuries.broken") and value >= 0 and value <= 255)
        if type(target) == "table" then target = "h" .. target.handle end
        if name == "injuries.broken" then s.broken[target] = value ~= 0 and value or nil return true end
        s.marks[target] = value ~= 0 and value or nil""")
sub("               killed = {}, flags = {}, marks = {}, addon_handlers = {}}",
    "               killed = {}, flags = {}, marks = {}, addon_handlers = {}, broken = {}, dropped = {}}")
sub("""        env.characters.set_limb_strength = function""", """        caps["characters.drop_held"] = true
        env.characters.drop_held = function(target, side)
            assert(side == "right" or side == "left", "side")
            if type(target) == "table" then target = "h" .. target.handle end
            s.dropped[#s.dropped + 1] = tostring(target) .. ":" .. side
            return true
        end
        env.characters.set_limb_strength = function""")
sub('print("injuries harness: all checks passed")', """-- Broken bones reach ExCamera as bits, and a badly broken arm drops its weapon; a cut arm does not.
local k = new()
k.fire("runtime.phase", {phase = "session"})
k.fire("character.hit", hit(13, 0.3, 2, {handle = 70}))      -- right forearm, mace: broken, severity 1
assert(k.broken.h70 == 1 << 5, "forearm bit " .. tostring(k.broken.h70))
assert(k.dropped[1] == "h70:right", "dropped " .. tostring(k.dropped[1]))
k.fire("character.hit", hit(6, 0.3, 2, {handle = 70}))       -- left shin
assert(k.broken.h70 == (1 << 5) | (1 << 3), "two bones")
k.fire("character.hit", hit(15, 0.3, 1, {handle = 70}))      -- left upper arm, sword: cut, not broken
assert(#k.dropped == 1 and k.broken.h70 == (1 << 5) | (1 << 3), "a cut drops nothing and sets no bit")
k.addon_handlers["injuries.heal"]({target = {handle = 70}, amount = 3})
k.tick(1)
assert(k.broken.h70 == nil, "healed bones clear the mark")

print("injuries harness: all checks passed")""")
p.write_text(t, encoding="utf-8")
print("ok")
