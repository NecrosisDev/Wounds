"""Harness: handle targets (runtime r37c) for limb strength, the mend mark, the neck kill and heals."""
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "tests" / "harness.lua"
t = p.read_text(encoding="utf-8")


def sub(old, new):
    global t
    assert t.count(old) == 1, old[:60]
    t = t.replace(old, new)


sub("""            assert(target == "player" or math.type(target) == "integer", "target")""",
    """            if type(target) == "table" then
                assert(math.type(target.handle) == "integer" and target.handle > 0, "handle")
                target = "h" .. target.handle
            end
            assert(target == "player" or math.type(target) == "integer" or target:find("^h%d+$"), "target")""")
sub("""        assert(name == "injuries.mend" and value >= 0 and value <= 255)""",
    """        assert(name == "injuries.mend" and value >= 0 and value <= 255)
        if type(target) == "table" then target = "h" .. target.handle end""")
sub("""            rows[#rows + 1] = {record_id = id, name = "Bandit", dead = false, damage = function(self, o)""",
    """            rows[#rows + 1] = {record_id = id, handle = id * 10, name = "Bandit", dead = false, damage = function(self, o)""")
sub('print("injuries harness: all checks passed")', """-- With handles (runtime r37c): one character, not every one sharing its record.
local h = new()
h.fire("runtime.phase", {phase = "session"})
h.fire("character.hit", hit(3, 0.3, 2, {handle = 70}))
assert(h.sent.h70 and h.sent.h70[3] < 0.5 and h.sent[7] == nil, "limb strength by handle")
h.addon_handlers["injuries.heal"]({target = {handle = 70}, amount = 1}, "com.necrosis.bodyschool")
assert(h.sent.h70[3] == 1 and h.marks.h70 == 8, "healed and marked by handle")
h.fire("character.hit", hit(10, 0.3, 2, {handle = 80, record_id = 7}))
h.run_afters()
assert(h.killed[8] and h.killed[7] == nil, "the neck kill finds the row by handle, not the record")

print("injuries harness: all checks passed")""")
p.write_text(t, encoding="utf-8")
print("ok")
