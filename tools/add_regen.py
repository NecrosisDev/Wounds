"""Injuries: the cross-mod regeneration API (shared flags) and the mend mark for ExCamera."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent


def sub(rel, old, new):
    p = root / rel
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (rel, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8")


sub("scripts/injuries.lua", "-- The strength (0..1) each limb part of a target should have now.", """-- Regeneration another mod asked for (README, "For other mods"): `rate` is severity per
-- second (a full injury mends in 1/rate seconds), below 0 mends at once; `mask` limits it to
-- parts (bit part-1), 0 for every part. No rest needed. Returns the parts that healed fully.
function M.regenerate(target, dt, rate, mask)
    local healed = {}
    local list = injuries[target]
    if not list then return healed end
    for part, injury in pairs(list) do
        if mask == 0 or (mask >> (part - 1)) & 1 == 1 then
            injury.severity = rate < 0 and 0 or injury.severity - dt * rate
            if injury.severity <= 0 then
                list[part] = nil
                healed[#healed + 1] = {target = target, part = part, kind = injury.kind}
            end
        end
    end
    strain[target] = nil
    if next(list) == nil then injuries[target] = nil end
    return healed
end

-- The injured parts of a target as a bit mask (bit part-1).
function M.mask(target)
    local m = 0
    for part in pairs(injuries[target] or {}) do m = m | (1 << (part - 1)) end
    return m
end

-- The strength (0..1) each limb part of a target should have now.""")

sub("scripts/config.lua", "    notices = true,\n", """    -- While another mod regenerates a character, ExCamera closes its painted wounds over
    -- this many seconds (the "injuries.mend" mark's value).
    mend_fade_seconds = 8,
    notices = true,
""")

sub("scripts/main.lua", "local last_tick = nil\nlocal function tick()", """-- Regeneration requested by other mods through shared flags (README, "For other mods"), and
-- the "injuries.mend" mark that tells ExCamera to close the painted wounds meanwhile.
local mending = {}   -- [target] = time the mend mark may be cleared
local function flags_ok() return api.has_capability("script.flags") and script_flags ~= nil end
local function flag_key(target) return target == "player" and "player" or string.format("%d", target) end

local function set_mend(target, now)
    local can = api.has_capability("characters.marks") and characters and characters.set_mark
    if now == nil then
        if can then pcall(characters.set_mark, target, "injuries.mend", 0) end
        mending[target] = nil
    elseif not mending[target] then
        if can then pcall(characters.set_mark, target, "injuries.mend", math.floor(cfg.mend_fade_seconds)) end
        mending[target] = now
    end
end

local function regenerate(now, dt, healed)
    if not flags_ok() then return end
    local seen = {}
    local function one(target)
        if seen[target] then return end
        seen[target] = true
        local key = flag_key(target)
        local rate = script_flags.get("injuries_heal_" .. key)
        if rate and rate ~= 0 then
            local mask = script_flags.get("injuries_parts_" .. key) or 0
            for _, h in ipairs(injuries.regenerate(target, dt, rate < 0 and -1 or rate / 1000, mask)) do
                healed[#healed + 1] = h
            end
            set_mend(target, now)
            -- Keep the mark while it runs; a one-shot (below 0) holds it for one full fade.
            mending[target] = now + (rate < 0 and cfg.mend_fade_seconds or 1.5)
            if rate < 0 then script_flags.set("injuries_heal_" .. key, nil) end
        elseif mending[target] and now >= mending[target] then
            set_mend(target, nil)
        end
    end
    one("player")
    for _, target in ipairs(injuries.targets()) do one(target) end
    local marked = {}
    for target in pairs(mending) do marked[#marked + 1] = target end
    for _, target in ipairs(marked) do one(target) end
    script_flags.set("injuries_hurt_player", injuries.mask("player"))
end

local last_tick = nil
local function tick()""")

sub("scripts/main.lua", """    local healed = injuries.tick(now, dt)
""", """    local healed = injuries.tick(now, dt)
    regenerate(now, dt, healed)
""")
sub("scripts/main.lua", """        injuries.level_changed()
""", """        injuries.level_changed()
        mending = {}   -- the runtime forgets marks at a level change
""")
sub("manifest.toml", """            "player.damage", "characters.damage", "characters.read"]""",
    """            "player.damage", "characters.damage", "characters.read",
            "script.flags", "characters.marks"]
# Other mods ask for regeneration through script flags (README, "For other mods"); the
# "injuries.mend" mark tells ExCamera to close the painted wounds meanwhile.""")
print("ok")
