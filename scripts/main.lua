-- Injuries: hard enough blows to a limb break the bone (blunt) or cut the muscle
-- (edges and points). The limb's muscles then pull weaker: a broken leg limps and
-- gives way, a cut arm swings weak and hangs. Injuries heal slowly once the
-- character has rested a while without being hit. The runtime scales each limb
-- part's muscle strength inside the game's own joint solver
-- (characters.set_limb_strength, RUNTIME-REQUESTS.md); without it the addon only
-- keeps track and says so once.
local defaults = require("config")
local injuries = require("injuries")

local cfg = {}
for k, v in pairs(defaults) do cfg[k] = v end
injuries.init(cfg)

local ROWS = {
    {key = "enabled", label = "Injuries", type = "toggle", default = defaults.enabled,
     help = "Hard blows to arms and legs break bones (blunt) or cut muscles (edges), weakening the limb"},
    {key = "npcs", label = "Others", type = "toggle", default = defaults.npcs,
     help = "Other characters get injured too, not only you"},
    {type = "header", label = "Thresholds"},
    {key = "break_at", label = "Bone", type = "number", default = defaults.break_at, min = 0.03, max = 0.5,
     step = 0.01, format = "percent", help = "Blunt damage to one limb part in one hit, as % of health, that breaks the bone"},
    {key = "disable_at", label = "Muscle", type = "number", default = defaults.disable_at, min = 0.03, max = 0.5,
     step = 0.01, format = "percent", help = "Edge or point damage to one limb part in one hit, as % of health, that cuts the muscle"},
    {key = "neck_break_at", label = "Neck", type = "number", default = defaults.neck_break_at, min = 0.05,
     max = 1, step = 0.01, format = "percent", help = "Blunt damage to the head in one hit, as % of health, that breaks the neck"},
    {key = "neck_kills", label = "Lethal neck", type = "toggle", default = defaults.neck_kills,
     help = "A hard enough blunt blow to the head breaks the neck and kills, you or anyone"},
    {key = "sever", label = "Severing", type = "toggle", default = defaults.sever,
     help = "A hard cut can take an arm or leg off; without a leg a character stays on the ground (needs the runtime)"},
    {key = "sever_at", label = "Sever", type = "number", default = defaults.sever_at, min = 0.1, max = 1, step = 0.05,
     format = "percent", help = "Edge damage to an arm or leg in one hit, as % of health, that takes it off"},
    {type = "header", label = "Healing"},
    {key = "heal_speed", label = "Speed", type = "number", default = defaults.heal_speed, min = 0, max = 4,
     step = 0.25, help = "0 never heals; at 1x a bad break mends in ten minutes of rest, a cut in three"},
    {key = "rest_seconds", label = "Delay", type = "number", default = defaults.rest_seconds, min = 0, max = 120,
     step = 5, help = "Seconds without being hit before healing starts"},
    {key = "notices", label = "Messages", type = "toggle", default = defaults.notices,
     help = "On-screen messages when you're injured or healed"},
}
-- The same rows without sub-headers and % display, for a runtime before 0.28.0-r42.
local PLAIN = {}
for _, row in ipairs(ROWS) do
    if row.key then
        local copy = {}
        for k, v in pairs(row) do if k ~= "format" then copy[k] = v end end
        PLAIN[#PLAIN + 1] = copy
    end
end

local can_apply = api.has_capability("characters.limb_strength") and characters and characters.set_limb_strength
local warned = false

local function say(text)
    if cfg.notices and api.has_capability("ui.notify") and ui and ui.notify then ui.notify(text) end
end

local function readable(part) return (injuries.NAMES[part] or "limb"):gsub("_", " ") end

-- Bookkeeping keys: "player", "h<handle>" for one live character (character.hit `handle`, runtime
-- r37c), or a record_id where the runtime gives no handle. The runtime target for each key:
local function runtime_target(key)
    if type(key) == "string" and key:sub(1, 1) == "h" then return {handle = math.tointeger(tonumber(key:sub(2)))} end
    return key
end

-- A key from a target value another mod or event gives: "player", a record_id, or a table with a handle.
local function key_of(target)
    if target == "player" then return "player" end
    if type(target) == "table" and math.type(target.handle) == "integer" and target.handle > 0 then
        return "h" .. string.format("%d", target.handle)
    end
    if math.type(target) == "integer" then return target end
    return nil
end

local function send(target)
    if not can_apply then
        if not warned then
            warned = true
            log.warn("characters.set_limb_strength is not in this runtime: injuries are tracked but limbs keep their strength")
        end
        return
    end
    injuries.apply(target, function(part, value)
        local ok, result = pcall(characters.set_limb_strength, runtime_target(target), part, value)
        if not ok then log.warn("set_limb_strength failed: " .. tostring(result)) end
        return ok and result == true
    end)
end

-- Severed limbs: bits per target (as "injuries.severed" for ExCamera) and the stump's bleeding.
local severed = {}      -- [target] = bits
local stump_bleed = {}  -- [target] = seconds of bleeding left
local function sever(target, hit_part)
    local cut = injuries.SEVER[hit_part]
    if not cut or not cfg.sever then return false end
    -- A leg only where the character can be kept on the ground afterwards (requested keep_down).
    local keep_down = api.has_capability("characters.keep_down") and characters.keep_down
    if cut.leg and not keep_down then return false end
    if (severed[target] or 0) & (1 << cut.bit) ~= 0 then return false end
    if not (api.has_capability("characters.sever") and characters.sever) then return false end
    local ok, done = pcall(characters.sever, runtime_target(target), cut.part)
    if not ok or done ~= true then
        if not ok then log.warn("sever failed: " .. tostring(done)) end
        return false
    end
    severed[target] = (severed[target] or 0) | (1 << cut.bit)
    if api.has_capability("characters.marks") and characters.set_mark then
        pcall(characters.set_mark, runtime_target(target), "injuries.severed", severed[target])
    end
    if cut.side and api.has_capability("characters.drop_held") and characters.drop_held then
        pcall(characters.drop_held, runtime_target(target), cut.side)
    end
    if cut.leg then pcall(characters.keep_down, runtime_target(target), true) end
    stump_bleed[target] = cfg.sever_bleed
    return true
end

-- The broken-bone bits ExCamera reads ("injuries.broken"), sent when they change.
local broken_sent = {}
local function send_broken(target)
    if not (api.has_capability("characters.marks") and characters and characters.set_mark) then return end
    local bits = injuries.broken_bits(target)
    if (broken_sent[target] or 0) == bits then return end
    if pcall(characters.set_mark, runtime_target(target), "injuries.broken", bits) then
        broken_sent[target] = bits ~= 0 and bits or nil
    end
end

local function sync_all()
    for _, target in ipairs(injuries.targets()) do send(target) send_broken(target) end
    for target in pairs(broken_sent) do send_broken(target) end
end

local scar_of_player = function() return 0 end -- set once the burn bookkeeping exists (below)
local function save_player()
    if not (api.has_capability("storage.save") and save_data) then return end
    local scar = scar_of_player()
    save_data.set(injuries.encode() .. (scar > 0 and string.format("|S%.3f", scar) or "") ..
                  ((severed.player or 0) ~= 0 and string.format("|X%d", severed.player) or ""))
end

local function turn_off()
    injuries.clear_all()
    sync_all()
    save_player()
end

if api.has_capability("ui.settings") and settings and settings.define then
    if not pcall(settings.define, "Injuries", ROWS) then settings.define("Injuries", PLAIN) end
    for _, row in ipairs(PLAIN) do
        local v = settings.get(row.key)
        if v ~= nil then cfg[row.key] = v end
    end
    events.on("settings.changed", function(e)
        if cfg[e.key] == nil then return end
        cfg[e.key] = e.value
        if e.key == "enabled" and not e.value then turn_off() end
    end)
end

-- Weapon grips, read once per weapon record.
local grips = {}
local function weapon_of(id)
    if not id or not api.has_capability("items.stats") then return nil end
    if grips[id] == nil then
        local stats = items.stats(id)
        grips[id] = stats and stats.weapon or false
    end
    return grips[id] or nil
end

-- Death by the game's own damage applier, from a timer callback (where the staged calls are allowed).
local function break_neck(hit)
    timers.after(0, function()
        if hit.is_player then
            if api.has_capability("player.damage") and player and player.damage then player.damage(1, 2, true) end
            return
        end
        if not (api.has_capability("characters.damage") and api.has_capability("characters.read")) then
            log.warn("a broken neck needs characters.damage and characters.read")
            return
        end
        local snap = characters.snapshot()
        for _, c in ipairs(snap and snap.characters or {}) do
            local same = hit.handle and c.handle == hit.handle or (not hit.handle and c.record_id == hit.record_id)
            if same and c.damage and not c.dead then
                c:damage({health = 1, balance = 1, can_fall = true})
                return
            end
        end
    end)
end

events.on("character.hit", function(hit)
    if not cfg.enabled or hit.blocked or hit.parried or not hit.part then return end
    if not hit.is_player and not cfg.npcs then return end
    local target = hit.is_player and "player" or key_of(hit.handle and {handle = hit.handle} or hit.record_id)
    if target == nil then return end
    local blunt = injuries.blunt(hit, weapon_of(hit.weapon_id))
    if not blunt and (hit.health_damage or 0) >= cfg.sever_at and sever(target, hit.part) then
        if hit.is_player then
            say("Your " .. readable(hit.part) .. " is cut off.")
            save_player()
        end
        return -- the limb is gone: no injury to track on it
    end
    if injuries.neck(hit.part, hit.health_damage, blunt) then
        if hit.is_player then say("Your neck snaps.") end
        break_neck(hit)
        return
    end
    local injury = injuries.hit(target, hit.part, hit.health_damage, blunt, timers.now())
    if not injury then return end
    send(target)
    send_broken(target)
    -- A badly broken arm lets go of what its hand holds (requested runtime call; nothing without it).
    local side = injuries.ARM_SIDE[injury.part]
    if side and injury.kind == "broken" and injury.severity >= cfg.drop_at and
            api.has_capability("characters.drop_held") and characters.drop_held then
        local ok, err = pcall(characters.drop_held, runtime_target(target), side)
        if not ok then log.warn("drop_held failed: " .. tostring(err)) end
    end
    if hit.is_player then
        save_player()
        local where = readable(injury.part)
        if injury.kind == "broken" then say("Your " .. where .. " is broken.")
        else say("Your " .. where .. " is cut to the muscle.") end
    end
end)

-- Burns: level 0..1 per character, sent to ExCamera as the "injuries.burn" mark (0..255) when it moves
-- by a step, and to the runtime as soot and wear on what the character wears (requested call).
local burns = {}       -- [target] = level
local burn_peak = {}   -- [target] = the worst level this burn reached
local scars = {}       -- [target] = burn scar tissue 0..1, for good
local scar_sent = {}   -- [target] = mark value last sent
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
    burn_peak[target] = math.max(burn_peak[target] or 0, burns[target])
    burn_last[target] = timers.now()
    send_burn(target)
    if api.has_capability("characters.soil_worn") and characters.soil_worn then
        local ok, err = pcall(characters.soil_worn, runtime_target(target), {dirt = amount * 3, wear = amount})
        if not ok then log.warn("soil_worn failed: " .. tostring(err)) end
    end
    if target == "player" and before < 0.3 and burns[target] >= 0.3 then say("Your skin blisters from the fire.") end
end

scar_of_player = function() return scars.player or 0 end

local function send_scar(target)
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
        if target == "player" then save_player() end
    end
    if not burns[target] then burn_peak[target] = nil end
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
    for target in pairs(burn_peak) do scar_from(target) end
    for target in pairs(burn_sent) do send_burn(target) end
    for target in pairs(burns) do send_burn(target) end
end

if addons and addons.on then
    local ok, err = pcall(addons.on, "injuries.burn", on_burn)
    if not ok then log.warn("addons.on(\"injuries.burn\") failed: " .. tostring(err)) end
end

-- Regeneration asked for by other mods (Body School's Regenerate) through the runtime's addon
-- channel, and the "injuries.mend" mark that tells ExCamera to close the painted wounds meanwhile.
local mending = {}   -- [target] = time the mend mark may be cleared

local function set_mend(target, until_time)
    local can = api.has_capability("characters.marks") and characters and characters.set_mark
    if until_time == nil then
        if can then pcall(characters.set_mark, runtime_target(target), "injuries.mend", 0) end
        mending[target] = nil
        return
    end
    if not mending[target] and can then
        pcall(characters.set_mark, runtime_target(target), "injuries.mend", math.floor(cfg.mend_fade_seconds))
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

-- addons.send("com.necrosis.injuries", "injuries.heal", {target = "player", a record_id or a row/event
-- with a `handle`, amount = 0..1}), delivered as fn(value, from):
-- heals `amount` of severity across the target's injured parts, worst first, with no rest needed.
-- Sent once a second while a power is held, the mend mark stays on until 1.5 s after the last one.
local function on_heal(a, _from)
    local msg = a
    if type(msg) ~= "table" or not cfg.enabled then return end
    local target = key_of(msg.target)
    if target == nil then return end
    local amount = tonumber(msg.amount)
    if not amount or amount ~= amount or amount <= 0 then return end
    local now = timers.now()
    set_mend(target, now + 1.5)
    local healed = injuries.heal_amount(target, math.min(amount, 1))
    announce(healed)
    send(target)
    if burns[target] then
        burns[target] = burns[target] - math.min(amount, 1) * cfg.burn_mend
        if burns[target] <= 0 then burns[target] = nil end
        send_burn(target)
        scar_from(target)
    end
end

if addons and addons.on then
    local ok, err = pcall(addons.on, "injuries.heal", on_heal)
    if not ok then log.warn("addons.on(\"injuries.heal\") failed: " .. tostring(err)) end
end

local last_tick = nil
local function tick()
    local now = timers.now()
    local dt = last_tick and math.max(now - last_tick, 0) or 0
    last_tick = now
    announce(injuries.tick(now, dt))
    for target, left in pairs(stump_bleed) do
        stump_bleed[target] = left - dt
        if stump_bleed[target] <= 0 then stump_bleed[target] = nil end
        if dt > 0 then
            local amount = 0.006 * dt
            if target == "player" then
                if api.has_capability("player.damage") and player and player.damage then player.damage(0, amount, false) end
            elseif api.has_capability("characters.damage") and api.has_capability("characters.read") then
                local key = runtime_target(target)
                local snap = characters.snapshot()
                for _, c in ipairs(snap and snap.characters or {}) do
                    local same = type(key) == "table" and c.handle == key.handle or c.record_id == key
                    if same and c.damage and not c.dead then c:damage({health = amount, balance = 0, can_fall = false}) break end
                end
            end
        end
    end
    heal_burns(now, dt)
    expire_mends(now)
    sync_all()
end

local timer = nil
events.on("runtime.phase", function(e)
    if e.phase == "session" then
        injuries.level_changed()
        mending = {}   -- the runtime forgets marks at a level change
        broken_sent = {}
        local player_scar = scars.player
        burns, burn_sent, burn_last, burn_peak, scars, scar_sent = {}, {}, {}, {}, {}, {}
        scars.player = player_scar
        if api.has_capability("storage.save") and save_data then
            local saved = save_data.get() or ""
            injuries.decode(saved)
            local scar = tonumber(saved:match("|S([%d%.]+)"))
            if scar and scar > 0 then scars.player = math.min(scar, 1) end
        end
        if scars.player then send_scar("player") end
        local saved_bits = tonumber((api.has_capability("storage.save") and save_data and save_data.get() or ""):match("|X(%d+)"))
        severed, stump_bleed = {}, {}
        if saved_bits then
            for hit_part, cut in pairs(injuries.SEVER) do
                if hit_part == cut.part and saved_bits & (1 << cut.bit) ~= 0 then sever("player", hit_part) end
            end
            stump_bleed = {}
        end
        if not cfg.enabled then injuries.clear_all() end
        last_tick = nil
        if not timer then timer = timers.every(cfg.tick_seconds, tick) end
        sync_all()
    else
        if timer then timers.cancel(timer) timer = nil end
    end
end)
