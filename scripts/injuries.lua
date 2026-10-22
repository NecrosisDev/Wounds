-- Injury bookkeeping, free of the runtime: which limb parts of which character are
-- broken (blunt) or disabled (cut), how badly, and the muscle strength each part
-- should have. main.lua feeds it hits and ticks and applies its strengths.
local M = {}

-- Body parts, 1-based in the game's order (API.md, character.hit `part`).
M.NAMES = {"pelvis", "right_thigh", "right_shin", "right_foot", "left_thigh", "left_shin", "left_foot",
           "belly", "chest", "head", "right_shoulder", "right_upper_arm", "right_forearm",
           "left_shoulder", "left_upper_arm", "left_forearm", "right_hand", "left_hand"}
-- The limb parts and what hangs below each: an injured part weakens its own joint fully
-- and the joints further down the limb by half.
M.BELOW = {
    [2] = {3, 4}, [3] = {4}, [4] = {},
    [5] = {6, 7}, [6] = {7}, [7] = {},
    [11] = {12, 13, 17}, [12] = {13, 17}, [13] = {17}, [17] = {},
    [14] = {15, 16, 18}, [15] = {16, 18}, [16] = {18}, [18] = {},
}

local cfg
local injuries = {}   -- [target] = {[part] = {kind, severity}}
local strain = {}     -- [target] = {[part] = health damage piled up since the last rest}
local last_hit = {}   -- [target] = time of the last hit
local applied = {}    -- [target] = {[part] = strength last sent}

function M.init(config) cfg = config end

local function clamp(x, lo, hi) return x < lo and lo or (x > hi and hi or x) end

-- A blow is blunt unless the weapon's grip cuts or points more than it crushes.
function M.blunt(hit, weapon)
    if hit.source == "impact" or not hit.weapon_id then return true end
    local grip = weapon and weapon.grip
    if not grip then return false end
    return (grip.crush or 0) > math.max(grip.cut or 0, grip.point or 0)
end

-- How hard a cut chops through a limb, compared with cfg.sever_at. A blade takes a limb off when its
-- edge, its weight and the blow together beat the limb's thickness:
-- * the blow: this hit's health damage (after armour) plus half the damage this part has already
--   taken since its last rest;
-- * the edge: no edge (cut under 0.2, the game's own grip numbers) never severs; a blunt blow never does;
-- * the weight: heft against a typical one-handed sword (0.45): a dagger chops at a third, a two-handed
--   sword or axe at about 1.3;
-- * the limb: a wrist or ankle goes easily, a forearm or shin less, an upper arm or thigh hardly;
-- * earlier wounds: a part already cut through the muscle chops easier by its severity, a broken
--   bone by 1.4 more.
M.CHOP_PART = {[17] = 1.6, [18] = 1.6, [13] = 1.15, [16] = 1.15, [12] = 0.75, [15] = 0.75,
               [4] = 1.3, [7] = 1.3, [3] = 0.9, [6] = 0.9, [2] = 0.55, [5] = 0.55}
function M.chop(target, part, damage, weapon)
    local limb = M.CHOP_PART[part]
    if not limb or not damage or damage <= 0 then return 0 end
    local edge, heft = 1, 1
    if weapon then
        local cut = math.max(weapon.grip and weapon.grip.cut or 0, weapon.alternate_grip and weapon.alternate_grip.cut or 0)
        if cut < 0.2 then return 0 end
        edge = clamp(cut / 0.4, 0.6, 1.25)
        heft = clamp((weapon.heft or 0.45) / 0.45, 0.3, 1.6)
    end
    local blow = damage + 0.5 * ((strain[target] or {})[part] or 0)
    local wound = 1
    local old = (injuries[target] or {})[part]
    if old then wound = 1 + old.severity * (old.kind == "broken" and 1.4 or 1) end
    return blow * edge * heft * limb * wound
end

-- One hit. Returns the new or worsened injury as {part, kind, severity, new}, or nil.
function M.hit(target, part, damage, blunt, now)
    last_hit[target] = now
    if not M.BELOW[part] or not damage or damage <= 0 then return nil end
    local s = strain[target] or {}
    strain[target] = s
    s[part] = (s[part] or 0) + damage
    local threshold = blunt and cfg.break_at or cfg.disable_at
    if s[part] < threshold then return nil end
    local kind = blunt and "broken" or "disabled"
    local severity = clamp(s[part] / (2 * threshold), 0.5, 1)
    s[part] = 0
    local list = injuries[target] or {}
    injuries[target] = list
    local old = list[part]
    if old then
        -- A break outranks a cut; either way the worse severity stays.
        if old.kind == "broken" then kind = "broken" end
        severity = math.max(severity, old.severity)
        if old.kind == kind and severity <= old.severity then return nil end
    end
    list[part] = {kind = kind, severity = severity}
    return {part = part, kind = kind, severity = severity, new = old == nil}
end

-- A broken neck: one blunt blow to the head (part 10) at or past the neck threshold.
function M.neck(part, damage, blunt)
    return cfg.neck_kills and blunt and part == 10 and (damage or 0) >= cfg.neck_break_at
end

-- Healing after rest. Returns the parts that healed fully, as {target, part, kind}.
function M.tick(now, dt)
    local healed = {}
    for target, list in pairs(injuries) do
        if now - (last_hit[target] or now) >= cfg.rest_seconds and cfg.heal_speed > 0 then
            for part, injury in pairs(list) do
                local span = injury.kind == "broken" and cfg.heal_broken or cfg.heal_disabled
                injury.severity = injury.severity - dt * cfg.heal_speed / span
                if injury.severity <= 0 then
                    list[part] = nil
                    healed[#healed + 1] = {target = target, part = part, kind = injury.kind}
                end
            end
            if strain[target] then strain[target] = nil end
            if next(list) == nil then injuries[target] = nil end
        end
    end
    return healed
end

-- Healing another mod asked for: takes `amount` of severity off the target's injuries, worst
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

-- Broken bones as ExCamera's "injuries.broken" bits: one per limb bone (thigh, shin with foot, upper arm
-- with shoulder, forearm with hand; right then left), so a mark value of 0..255 holds them all.
M.BONE_BIT = {[2] = 0, [3] = 1, [4] = 1, [5] = 2, [6] = 3, [7] = 3,
              [11] = 4, [12] = 4, [13] = 5, [17] = 5, [14] = 6, [15] = 6, [16] = 7, [18] = 7}
-- The hand each arm part belongs to.
M.ARM_SIDE = {[11] = "right", [12] = "right", [13] = "right", [17] = "right",
              [14] = "left", [15] = "left", [16] = "left", [18] = "left"}

-- Severing: the part the cut lands on, the part the runtime cuts at (the joint to its parent), the
-- "injuries.severed" bit and the hand that lets go.
M.SEVER = {
    [12] = {part = 12, bit = 4, side = "right"}, [13] = {part = 13, bit = 5, side = "right"}, [17] = {part = 13, bit = 5, side = "right"},
    [15] = {part = 15, bit = 6, side = "left"},  [16] = {part = 16, bit = 7, side = "left"},  [18] = {part = 16, bit = 7, side = "left"},
    -- Legs: at the hip (thigh) or the knee (shin, foot); a character missing one stays down.
    [2] = {part = 2, bit = 0, leg = true}, [3] = {part = 3, bit = 1, leg = true}, [4] = {part = 3, bit = 1, leg = true},
    [5] = {part = 5, bit = 2, leg = true}, [6] = {part = 6, bit = 3, leg = true}, [7] = {part = 6, bit = 3, leg = true},
}

function M.broken_bits(target)
    local bits = 0
    for part, injury in pairs(injuries[target] or {}) do
        local bit = M.BONE_BIT[part]
        if injury.kind == "broken" and bit then bits = bits | (1 << bit) end
    end
    return bits
end

-- The injured parts of a target as a bit mask (bit part-1).
function M.mask(target)
    local m = 0
    for part in pairs(injuries[target] or {}) do m = m | (1 << (part - 1)) end
    return m
end

-- The strength (0..1) each limb part of a target should have now.
function M.strengths(target)
    local out = {}
    for part in pairs(M.BELOW) do out[part] = 1 end
    for part, injury in pairs(injuries[target] or {}) do
        local broken = injury.kind == "broken" and (part >= 11 and cfg.broken_arm_loss or cfg.broken_loss)
        local loss = injury.severity * (broken or cfg.disabled_loss)
        out[part] = math.min(out[part], 1 - loss)
        for _, below in ipairs(M.BELOW[part]) do out[below] = math.min(out[below], 1 - loss * 0.5) end
    end
    for part, v in pairs(out) do out[part] = clamp(v, 0.05, 1) end
    return out
end

-- The changes to send for a target: {part = strength} for parts that moved by more than
-- 0.02 (or reached 1) since the last send. `send(part, value)` returns true when applied.
function M.apply(target, send)
    local was = applied[target] or {}
    applied[target] = was
    for part, value in pairs(M.strengths(target)) do
        local last = was[part] or 1
        if math.abs(value - last) > 0.02 or (value == 1 and last ~= 1) then
            if send(part, value) then was[part] = value end
        end
    end
    if next(injuries[target] or {}) == nil then
        local clear = true
        for _, v in pairs(was) do if v ~= 1 then clear = false end end
        if clear then applied[target] = nil end
    end
end

function M.targets()
    local out = {}
    for target in pairs(injuries) do out[#out + 1] = target end
    for target in pairs(applied) do if not injuries[target] then out[#out + 1] = target end end
    return out
end

function M.injured(target) return injuries[target] end

-- The runtime forgets every strength at a level change: start from scratch, keeping the
-- player's injuries so they can be sent again.
function M.level_changed()
    local player = injuries.player
    injuries, strain, last_hit, applied = {}, {}, {}, {}
    injuries.player = player
end

-- One character is gone (a new arena round, or the row now belongs to someone else): drop
-- everything kept for it. Nothing is sent: the runtime's held strength went with the old body.
function M.forget(target)
    injuries[target], strain[target], last_hit[target], applied[target] = nil, nil, nil, nil
end

-- Everything off (the setting was switched off): what was sent must go back to 1.
function M.clear_all()
    for _, list in pairs(injuries) do for part in pairs(list) do list[part] = nil end end
    strain, last_hit = {}, {}
end

-- The player's injuries in a save: "part:k:severity;..." with k b (broken) or d (cut).
function M.encode()
    local parts = {}
    for part, injury in pairs(injuries.player or {}) do
        parts[#parts + 1] = string.format("%d:%s:%.3f", part, injury.kind == "broken" and "b" or "d", injury.severity)
    end
    table.sort(parts)
    return table.concat(parts, ";")
end

function M.decode(text)
    local list = {}
    for part, k, severity in string.gmatch(text or "", "(%d+):([bd]):([%d%.]+)") do
        part, severity = tonumber(part), tonumber(severity)
        if M.BELOW[part] and severity and severity > 0 then
            list[part] = {kind = k == "b" and "broken" or "disabled", severity = clamp(severity, 0, 1)}
        end
    end
    injuries.player = next(list) and list or nil
end

return M
