"""Injuries: publish broken bones as the "injuries.broken" mark (one bit per limb bone, for ExCamera's
fracture bruise) and let a broken arm drop what its hand holds (requested runtime call)."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent


def sub(rel, old, new):
    p = root / rel
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (rel, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8")


sub("scripts/injuries.lua", "-- The injured parts of a target as a bit mask (bit part-1).", """-- Broken bones as ExCamera's "injuries.broken" bits: one per limb bone (thigh, shin with foot, upper arm
-- with shoulder, forearm with hand; right then left), so a mark value of 0..255 holds them all.
M.BONE_BIT = {[2] = 0, [3] = 1, [4] = 1, [5] = 2, [6] = 3, [7] = 3,
              [11] = 4, [12] = 4, [13] = 5, [17] = 5, [14] = 6, [15] = 6, [16] = 7, [18] = 7}
-- The hand each arm part belongs to.
M.ARM_SIDE = {[11] = "right", [12] = "right", [13] = "right", [17] = "right",
              [14] = "left", [15] = "left", [16] = "left", [18] = "left"}

function M.broken_bits(target)
    local bits = 0
    for part, injury in pairs(injuries[target] or {}) do
        local bit = M.BONE_BIT[part]
        if injury.kind == "broken" and bit then bits = bits | (1 << bit) end
    end
    return bits
end

-- The injured parts of a target as a bit mask (bit part-1).""")

sub("scripts/main.lua", """local function sync_all()""", """-- The broken-bone bits ExCamera reads ("injuries.broken"), sent when they change.
local broken_sent = {}
local function send_broken(target)
    if not (api.has_capability("characters.marks") and characters and characters.set_mark) then return end
    local bits = injuries.broken_bits(target)
    if (broken_sent[target] or 0) == bits then return end
    if pcall(characters.set_mark, runtime_target(target), "injuries.broken", bits) then
        broken_sent[target] = bits ~= 0 and bits or nil
    end
end

local function sync_all()""")
sub("scripts/main.lua", """local function sync_all()
    for _, target in ipairs(injuries.targets()) do send(target) end""", """local function sync_all()
    for _, target in ipairs(injuries.targets()) do send(target) send_broken(target) end
    for target in pairs(broken_sent) do send_broken(target) end""")
sub("scripts/main.lua", """    if not injury then return end
    send(target)""", """    if not injury then return end
    send(target)
    send_broken(target)
    -- A badly broken arm lets go of what its hand holds (requested runtime call; nothing without it).
    local side = injuries.ARM_SIDE[injury.part]
    if side and injury.kind == "broken" and injury.severity >= cfg.drop_at and
            api.has_capability("characters.drop_held") and characters.drop_held then
        local ok, err = pcall(characters.drop_held, runtime_target(target), side)
        if not ok then log.warn("drop_held failed: " .. tostring(err)) end
    end""")
sub("scripts/main.lua", """        mending = {}   -- the runtime forgets marks at a level change""",
    """        mending = {}   -- the runtime forgets marks at a level change
        broken_sent = {}""")
sub("scripts/config.lua", "    neck_kills = true,\n", """    neck_kills = true,
    -- A broken arm this bad (severity 0.5..1) drops what its hand holds.
    drop_at = 0.6,
""")
sub("manifest.toml", """            "player.damage", "characters.damage", "characters.read", "characters.marks"]""",
    """            "player.damage", "characters.damage", "characters.read", "characters.marks",
            "characters.drop_held"]
# characters.drop_held is requested from the runtime (RUNTIME-REQUESTS.md, section 3): a badly broken
# arm drops what its hand holds. "injuries.broken" (bits per limb bone) is ExCamera's fracture bruise.""")
print("ok")
