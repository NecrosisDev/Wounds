"""Injuries: a broken arm goes nearly limp (hangs from the break); a broken leg keeps a little drive so it
buckles and drags instead of folding outright."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent


def sub(rel, old, new):
    p = root / rel
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (rel, old[:60])
    p.write_text(t.replace(old, new), encoding="utf-8")


sub("scripts/config.lua", "    broken_loss = 0.85,\n",
    "    broken_loss = 0.85,      -- a leg: it buckles and drags but still bears a little\n"
    "    broken_arm_loss = 0.95,  -- an arm: it hangs from the break\n")
sub("scripts/injuries.lua",
    "        local loss = injury.severity * (injury.kind == \"broken\" and cfg.broken_loss or cfg.disabled_loss)",
    "        local broken = injury.kind == \"broken\" and (part >= 11 and cfg.broken_arm_loss or cfg.broken_loss)\n"
    "        local loss = injury.severity * (broken or cfg.disabled_loss)")
print("ok")
