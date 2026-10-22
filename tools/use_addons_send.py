"""Injuries: heal requests arrive through addons.on("injuries.heal") (the runtime's addon channel)
instead of script flags. Replaces the flag polling added by add_regen.py."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent


def sub(rel, old, new):
    p = root / rel
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (rel, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8")


main = "scripts/main.lua"
t = (root / main).read_text(encoding="utf-8")
start = t.index("-- Regeneration requested by other mods through shared flags")
end = t.index("local last_tick = nil")
(root / main).write_text(t[:start] + """-- Regeneration asked for by other mods (Body School's Regenerate) through the runtime's addon
-- channel, and the "injuries.mend" mark that tells ExCamera to close the painted wounds meanwhile.
local mending = {}   -- [target] = time the mend mark may be cleared

local function set_mend(target, until_time)
    local can = api.has_capability("characters.marks") and characters and characters.set_mark
    if until_time == nil then
        if can then pcall(characters.set_mark, target, "injuries.mend", 0) end
        mending[target] = nil
        return
    end
    if not mending[target] and can then
        pcall(characters.set_mark, target, "injuries.mend", math.floor(cfg.mend_fade_seconds))
    end
    mending[target] = until_time
end

local function expire_mends(now)
    local done = {}
    for target, until_time in pairs(mending) do if now >= until_time then done[#done + 1] = target end end
    for _, target in ipairs(done) do set_mend(target, nil) end
end

local function announce(healed)
    for _, h in ipairs(healed) do
        if h.target == "player" then say("Your " .. readable(h.part) .. " has healed.") end
    end
    for _, h in ipairs(healed) do if h.target == "player" then save_player() break end end
end

-- addons.send("com.necrosis.injuries", "injuries.heal", {target = "player" or record_id, amount = 0..1}):
-- heals `amount` of severity across the target's injured parts, worst first, with no rest needed.
-- Sent once a second while a power is held, the mend mark stays on until 1.5 s after the last one.
local function on_heal(a, b)
    local msg = type(a) == "table" and a or b
    if type(msg) ~= "table" or not cfg.enabled then return end
    local target = msg.target
    if target ~= "player" and math.type(target) ~= "integer" then return end
    local amount = tonumber(msg.amount)
    if not amount or amount ~= amount or amount <= 0 then return end
    local now = timers.now()
    set_mend(target, now + 1.5)
    local healed = injuries.heal_amount(target, math.min(amount, 1))
    announce(healed)
    send(target)
end

if addons and addons.on then
    local ok, err = pcall(addons.on, "injuries.heal", on_heal)
    if not ok then log.warn("addons.on(\\"injuries.heal\\") failed: " .. tostring(err)) end
end

""" + t[end:], encoding="utf-8")

sub(main, """    local healed = injuries.tick(now, dt)
    regenerate(now, dt, healed)
    for _, h in ipairs(healed) do
        if h.target == "player" then say("Your " .. readable(h.part) .. " has healed.") end
    end
    if #healed > 0 then save_player() end
""", """    announce(injuries.tick(now, dt))
    expire_mends(now)
""")

inj = "scripts/injuries.lua"
t = (root / inj).read_text(encoding="utf-8")
start = t.index("-- Regeneration another mod asked for")
end = t.index("-- The injured parts of a target as a bit mask")
(root / inj).write_text(t[:start] + """-- Healing another mod asked for: takes `amount` of severity off the target's injuries, worst
-- first, any rest carried to the next. No rest needed. Returns the parts that healed fully.
function M.heal_amount(target, amount)
    local healed = {}
    local list = injuries[target]
    if not list then return healed end
    local order = {}
    for part, injury in pairs(list) do order[#order + 1] = {part = part, injury = injury} end
    table.sort(order, function(x, y)
        if x.injury.severity ~= y.injury.severity then return x.injury.severity > y.injury.severity end
        return x.part < y.part
    end)
    for _, o in ipairs(order) do
        if amount <= 0 then break end
        local take = math.min(amount, o.injury.severity)
        o.injury.severity = o.injury.severity - take
        amount = amount - take
        if o.injury.severity <= 1e-6 then
            list[o.part] = nil
            healed[#healed + 1] = {target = target, part = o.part, kind = o.injury.kind}
        end
    end
    strain[target] = nil
    if next(list) == nil then injuries[target] = nil end
    return healed
end

""" + t[end:], encoding="utf-8")

sub("manifest.toml", """            "player.damage", "characters.damage", "characters.read",
            "script.flags", "characters.marks"]
# Other mods ask for regeneration through script flags (README, "For other mods"); the
# "injuries.mend" mark tells ExCamera to close the painted wounds meanwhile.""",
    """            "player.damage", "characters.damage", "characters.read", "characters.marks"]
# Other mods heal through the runtime's addon channel: addons.send("com.necrosis.injuries",
# "injuries.heal", {target, amount}); the "injuries.mend" mark tells ExCamera to close the
# painted wounds meanwhile.""")
print("ok")
