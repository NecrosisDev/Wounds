"""Injuries: healed burns leave scar tissue ("injuries.burnscar", 0..255): as a burn heals, the scar grows
toward 0.6 of the worst burn it reached, and stays. The player's burn scar is kept in the save."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent


def sub(rel, old, new):
    p = root / rel
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (rel, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8")


M = "scripts/main.lua"
sub(M, """local burns = {}       -- [target] = level""", """local burns = {}       -- [target] = level
local burn_peak = {}   -- [target] = the worst level this burn reached
local scars = {}       -- [target] = burn scar tissue 0..1, for good
local scar_sent = {}   -- [target] = mark value last sent""")
sub(M, """local function heal_burns(now, dt)""", """local function send_scar(target)
    if not (api.has_capability("characters.marks") and characters and characters.set_mark) then return end
    local value = math.floor((scars[target] or 0) * 255 + 0.5)
    if math.abs(value - (scar_sent[target] or 0)) < 4 then return end
    if pcall(characters.set_mark, runtime_target(target), "injuries.burnscar", value) then
        scar_sent[target] = value ~= 0 and value or nil
    end
end

-- As a burn heals, scar tissue grows toward 0.6 of its worst, and stays.
local function scar_from(target)
    local peak = burn_peak[target] or 0
    local healed = peak - (burns[target] or 0)
    local scar = math.max(scars[target] or 0, math.min(healed, peak * 0.6))
    if scar > (scars[target] or 0) then
        scars[target] = scar
        send_scar(target)
    end
    if not burns[target] then burn_peak[target] = nil end
end

local function heal_burns(now, dt)""")
sub(M, """    for _, target in ipairs(done) do burns[target] = nil end
    for target in pairs(burn_sent) do send_burn(target) end""", """    for _, target in ipairs(done) do burns[target] = nil end
    for target in pairs(burn_peak) do scar_from(target) end
    for target in pairs(burn_sent) do send_burn(target) end""")
sub(M, """    burns[target] = math.min(before + math.min(amount, 1) * cfg.burn_gain, 1)""",
    """    burns[target] = math.min(before + math.min(amount, 1) * cfg.burn_gain, 1)
    burn_peak[target] = math.max(burn_peak[target] or 0, burns[target])""")
sub(M, """        if burns[target] <= 0 then burns[target] = nil end
        send_burn(target)""", """        if burns[target] <= 0 then burns[target] = nil end
        send_burn(target)
        scar_from(target)""")
# Saved: the player's injuries, then "|S" and the burn scar.
sub(M, """local function save_player()
    if api.has_capability("storage.save") and save_data then save_data.set(injuries.encode()) end
end""", """local scar_of_player = function() return 0 end -- set once the burn bookkeeping exists (below)
local function save_player()
    if not (api.has_capability("storage.save") and save_data) then return end
    local scar = scar_of_player()
    save_data.set(injuries.encode() .. (scar > 0 and string.format("|S%.3f", scar) or ""))
end""")
sub(M, """local function send_scar(target)""", """scar_of_player = function() return scars.player or 0 end

local function send_scar(target)""")
sub(M, """    if scar > (scars[target] or 0) then
        scars[target] = scar
        send_scar(target)
    end""", """    if scar > (scars[target] or 0) then
        scars[target] = scar
        send_scar(target)
        if target == "player" then save_player() end
    end""")
sub(M, """        burns, burn_sent, burn_last = {}, {}, {}""", """        local player_scar = scars.player
        burns, burn_sent, burn_last, burn_peak, scars, scar_sent = {}, {}, {}, {}, {}, {}
        scars.player = player_scar"""),
sub(M, """        if api.has_capability("storage.save") and save_data then injuries.decode(save_data.get()) end""",
    """        if api.has_capability("storage.save") and save_data then
            local saved = save_data.get() or ""
            injuries.decode(saved)
            local scar = tonumber(saved:match("|S([%d%.]+)"))
            if scar and scar > 0 then scars.player = math.min(scar, 1) end
        end
        if scars.player then send_scar("player") end""")
print("ok")
