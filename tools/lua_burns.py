"""Injuries: burns. addons.on("injuries.burn", {target, part?, amount}) raises a character's burn level
(0..1), which ExCamera bakes into the skin (mark "injuries.burn", 0..255) and which can soot and wear
the clothes (requested characters.soil_worn); injuries.heal and rest bring it down."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent


def sub(rel, old, new):
    p = root / rel
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (rel, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8")


sub("scripts/config.lua", "    notices = true,\n", """    -- Burns (the Fire mod sends "injuries.burn"): each unit of fire damage raises the burn level by
    -- burn_gain (1 = charred); a full burn heals in burn_heal seconds of rest at speed 1, and every
    -- unit of injuries.heal takes off burn_mend of it.
    burn_gain = 4,
    burn_heal = 900,
    burn_mend = 0.5,
    notices = true,
""")

sub("scripts/main.lua", "local last_tick = nil\nlocal function tick()", """-- Burns: level 0..1 per character, sent to ExCamera as the "injuries.burn" mark (0..255) when it moves
-- by a step, and to the runtime as soot and wear on what the character wears (requested call).
local burns = {}       -- [target] = level
local burn_sent = {}   -- [target] = mark value last sent
local burn_last = {}   -- [target] = time of the last burn (healing waits for rest)
local function send_burn(target)
    if not (api.has_capability("characters.marks") and characters and characters.set_mark) then return end
    local value = math.floor((burns[target] or 0) * 255 + 0.5)
    if math.abs(value - (burn_sent[target] or 0)) < 4 and not (value == 0 and burn_sent[target]) then return end
    if pcall(characters.set_mark, runtime_target(target), "injuries.burn", value) then
        burn_sent[target] = value ~= 0 and value or nil
    end
end

-- addons.send("com.necrosis.injuries", "injuries.burn", {target = "player", a record_id or a row/event with a
-- `handle`, part = 1..18 (optional, not used yet), amount = fire damage this time, 0..1}).
local function on_burn(msg, _from)
    if type(msg) ~= "table" or not cfg.enabled then return end
    local target = key_of(msg.target)
    local amount = tonumber(msg.amount)
    if target == nil or not amount or amount ~= amount or amount <= 0 then return end
    local before = burns[target] or 0
    burns[target] = math.min(before + math.min(amount, 1) * cfg.burn_gain, 1)
    burn_last[target] = timers.now()
    send_burn(target)
    if api.has_capability("characters.soil_worn") and characters.soil_worn then
        local ok, err = pcall(characters.soil_worn, runtime_target(target), {dirt = amount * 3, wear = amount})
        if not ok then log.warn("soil_worn failed: " .. tostring(err)) end
    end
    if target == "player" and before < 0.3 and burns[target] >= 0.3 then say("Your skin blisters from the fire.") end
end

local function heal_burns(now, dt)
    local done = {}
    for target, level in pairs(burns) do
        if now - (burn_last[target] or now) >= cfg.rest_seconds and cfg.heal_speed > 0 then
            burns[target] = level - dt * cfg.heal_speed / cfg.burn_heal
            if burns[target] <= 0 then done[#done + 1] = target end
        end
    end
    for _, target in ipairs(done) do burns[target] = nil end
    for target in pairs(burn_sent) do send_burn(target) end
    for target in pairs(burns) do send_burn(target) end
end

if addons and addons.on then
    local ok, err = pcall(addons.on, "injuries.burn", on_burn)
    if not ok then log.warn("addons.on(\\"injuries.burn\\") failed: " .. tostring(err)) end
end

local last_tick = nil
local function tick()""")
sub("scripts/main.lua", """    announce(injuries.tick(now, dt))
""", """    announce(injuries.tick(now, dt))
    heal_burns(now, dt)
""")
# Regeneration also takes burns down.
sub("scripts/main.lua", """    local healed = injuries.heal_amount(target, math.min(amount, 1))
    announce(healed)
    send(target)
end""", """    local healed = injuries.heal_amount(target, math.min(amount, 1))
    announce(healed)
    send(target)
    if burns and burns[target] then
        burns[target] = burns[target] - math.min(amount, 1) * cfg.burn_mend
        if burns[target] <= 0 then burns[target] = nil end
        send_burn(target)
    end
end""")
sub("scripts/main.lua", """        broken_sent = {}""", """        broken_sent = {}
        burns, burn_sent, burn_last = {}, {}, {}""")
sub("manifest.toml", """            "characters.drop_held"]""", """            "characters.drop_held", "characters.soil_worn"]
# Burns arrive from the Fire mod on addons topic "injuries.burn"; "injuries.burn" (0..255) is ExCamera's
# baked scorch; characters.soil_worn (requested, section 4) soots and wears what a burning character wears.""")
print("ok")
