"""Harness: the addons channel instead of script flags for the regeneration checks."""
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "tests" / "harness.lua"
t = p.read_text(encoding="utf-8")


def sub(old, new):
    global t
    assert t.count(old) == 1, old[:60]
    t = t.replace(old, new)


sub("    env.player = {", """    if not opts.no_addons then
        env.addons = {on = function(name, fn) assert(name == "injuries.heal") s.addon_handlers[name] = fn return true end}
    end
    env.player = {""")
sub("               killed = {}, flags = {}, marks = {}}", "               killed = {}, flags = {}, marks = {}, addon_handlers = {}}")
start = t.index("-- Another mod regenerates:")
end = t.index('print("injuries harness: all checks passed")')
t = t[:start] + """-- Body School's Regenerate: addons.send(..., "injuries.heal", {target, amount}) once a second
-- heals worst first with no rest needed and holds the mend mark until 1.5 s after the last call.
local r = new()
r.fire("runtime.phase", {phase = "session"})
r.fire("character.hit", hit(3, 0.3, 2, {is_player = true, record_id = 1}))    -- severity 1 (break)
r.fire("character.hit", hit(13, 0.07, 1, {is_player = true, record_id = 1}))
r.fire("character.hit", hit(13, 0.07, 1, {is_player = true, record_id = 1}))  -- severity 0.7 (cut)
local heal = assert(r.addon_handlers["injuries.heal"], "registered")
heal({target = "player", amount = 0.4})
assert(r.marks.player == 8, "mend mark while healing")
assert(r.sent.player[3] < 1 and r.sent.player[13] < 1, "both still hurt")
heal({target = "player", amount = 0.4})     -- shin 1 -> 0.6 -> 0.6? worst first: 1 -> 0.6, then 0.7 -> 0.3
heal({target = "player", amount = 0.6})     -- 0.6 -> 0, rest 0 to the forearm? amounts: see below
heal({target = "player", amount = 0.3})
assert(r.sent.player[3] == 1 and r.sent.player[13] == 1, "all mended: " .. tostring(r.sent.player[3]) .. " " .. tostring(r.sent.player[13]))
assert(r.notes[#r.notes]:find("has healed"), r.notes[#r.notes])
r.tick(1)
assert(r.marks.player == 8, "mark still held just after")
r.tick(2)
assert(r.marks.player == nil, "mark cleared 1.5 s after the last heal")
-- An NPC by record id; junk messages are ignored.
r.fire("character.hit", hit(6, 0.3, 2))
heal({target = "7", amount = 1}) heal({target = 7, amount = -1}) heal("x")
assert(r.sent[7][6] < 1, "junk ignored")
heal({target = 7, amount = 1})
assert(r.sent[7][6] == 1 and r.marks[7] == 8, "NPC mended")
-- Without the channel nothing breaks.
local quiet = new({no_addons = true})
quiet.fire("runtime.phase", {phase = "session"})
quiet.tick(2)

""" + t[end:]
p.write_text(t, encoding="utf-8")
print("ok")
