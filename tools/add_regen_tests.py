"""Harness: script_flags and set_mark stubs, and the regeneration checks."""
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "tests" / "harness.lua"
t = p.read_text(encoding="utf-8")


def sub(old, new):
    global t
    assert t.count(old) == 1, old[:60]
    t = t.replace(old, new)


sub('["player.damage"] = true, ["characters.damage"] = true, ["characters.read"] = true}',
    '["player.damage"] = true, ["characters.damage"] = true, ["characters.read"] = true,\n'
    '                  ["script.flags"] = true, ["characters.marks"] = true}')
sub("               killed = {}}", "               killed = {}, flags = {}, marks = {}}")
sub("    env.player = {", """    env.script_flags = {
        get = function(name) return s.flags[name] end,
        set = function(name, value)
            assert(#name <= 32 and not name:find("[^%w_]"), "flag name " .. name)
            assert(value == nil or math.type(value) == "integer", "integer")
            s.flags[name] = value return true
        end,
    }
    env.player = {""")
sub("    env.characters = {snapshot = function()", """    env.characters_marks = true
    env.characters = {set_mark = function(target, name, value)
        assert(name == "injuries.mend" and value >= 0 and value <= 255)
        s.marks[target] = value ~= 0 and value or nil
        return true
    end, snapshot = function()""")
sub("        env.characters.set_limb_strength = function", "        env.characters.set_limb_strength = function")
sub('print("injuries harness: all checks passed")', """-- Another mod regenerates: a rate in thousandths of severity per second, no rest needed,
-- a part mask, a one-shot full mend, the published injured-part mask and the mend mark.
local r = new()
r.fire("runtime.phase", {phase = "session"})
r.fire("character.hit", hit(3, 0.3, 2, {is_player = true, record_id = 1}))
r.fire("character.hit", hit(13, 0.3, 1, {is_player = true, record_id = 1}))
r.tick(1)
assert(r.flags.injuries_hurt_player == (1 << 2) | (1 << 12), "published mask " .. tostring(r.flags.injuries_hurt_player))
r.flags.injuries_heal_player = 100           -- a full injury in 10 s
r.flags.injuries_parts_player = 1 << 12      -- the forearm only
r.tick(1)
assert(r.marks.player == 8, "mend mark while regenerating")
r.tick(11)
assert(r.sent.player[13] == 1 and r.sent.player[3] < 1, "only the masked forearm mended")
assert(r.notes[#r.notes]:find("right forearm has healed"), r.notes[#r.notes])
r.flags.injuries_heal_player = nil
r.flags.injuries_parts_player = nil
r.tick(3)
assert(r.marks.player == nil, "mark cleared after it stops")
r.flags.injuries_heal_player = -1             -- one-shot: mend everything now
r.tick(1)
assert(r.sent.player[3] == 1 and r.flags.injuries_heal_player == nil, "one-shot mended and cleared")
assert(r.marks.player == 8 and r.flags.injuries_hurt_player == 0, "mark held for the fade")
r.tick(9)
assert(r.marks.player == nil, "mark cleared after the fade")
-- An NPC by record id.
r.fire("character.hit", hit(6, 0.3, 2))
r.flags.injuries_heal_7 = 1000
r.tick(2)
assert(r.sent[7][6] == 1, "NPC mended")

print("injuries harness: all checks passed")""")
p.write_text(t, encoding="utf-8")
print("ok")
