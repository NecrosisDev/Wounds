"""wounds.inl: identify a struck part's character by +0x420, as the game's impact reads it."""
import sys
from pathlib import Path

p = Path(sys.argv[1])
t = p.read_bytes().decode("utf-8")
nl = "\r\n"
old_decl = "enum WoundKind : uint8_t { woundCut = 1, woundCrush = 2, woundThrust = 3 };" + nl
new_decl = old_decl + ("// A struck body part's character, where the game's weapon impact (0x159A60) reads its victim; that impact" + nl +
                       "// hands the same pointer to the damage applier, so it equals the record's victim." + nl +
                       "constexpr size_t woundPartCharacter = 0x420;" + nl)
assert t.count(old_decl) == 1
t = t.replace(old_decl, new_decl)
assert t.count("field::bodyPart::character") == 4
t = t.replace("field::bodyPart::character", "woundPartCharacter")
old_check = "    if (!w.owner || !intoPose(h.pose, h.point, true, w.local)) return;"
assert t.count(old_check) == 1
t = t.replace(old_check, "    if (!w.owner || w.owner != uintptr_t(h.victim) || !intoPose(h.pose, h.point, true, w.local)) return;")
# The pose (+0x2A0..+0x2D0) and mesh node lie below the owner field, so one range check covers them.
p.write_bytes(t.encode("utf-8"))
print("ok")
