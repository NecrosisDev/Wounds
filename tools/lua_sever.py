"""Injuries: severing (DISMEMBER-PLAN.md stage 3, arms). A cut of sever_at or more to an arm asks the
runtime to cut the joint (requested characters.sever); only when it did does the limb count as severed:
ExCamera's "injuries.severed" bits, the hand's grip let go, and heavy bleeding for a while. The player's
severed limbs are saved and cut again at the next session."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent


def sub(rel, old, new):
    p = root / rel
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (rel, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8")


sub("scripts/config.lua", "    notices = true,\n", """    -- Severing (arms): a cut this hard to an upper arm, forearm or hand takes the limb off at the
    -- shoulder or elbow, if the runtime can cut the joint; the stump then bleeds for sever_bleed seconds.
    sever = true,
    sever_at = 0.35,
    sever_bleed = 40,
    notices = true,
""")
sub("scripts/injuries.lua", "function M.broken_bits(target)", """-- Severing: the part the cut lands on, the part the runtime cuts at (the joint to its parent), the
-- "injuries.severed" bit and the hand that lets go.
M.SEVER = {
    [12] = {part = 12, bit = 4, side = "right"}, [13] = {part = 13, bit = 5, side = "right"}, [17] = {part = 13, bit = 5, side = "right"},
    [15] = {part = 15, bit = 6, side = "left"},  [16] = {part = 16, bit = 7, side = "left"},  [18] = {part = 16, bit = 7, side = "left"},
}

function M.broken_bits(target)""")

M = "scripts/main.lua"
sub(M, "-- The broken-bone bits ExCamera reads (\"injuries.broken\"), sent when they change.", """-- Severed limbs: bits per target (as "injuries.severed" for ExCamera) and the stump's bleeding.
local severed = {}      -- [target] = bits
local stump_bleed = {}  -- [target] = seconds of bleeding left
local function sever(target, hit_part)
    local cut = injuries.SEVER[hit_part]
    if not cut or not cfg.sever then return false end
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
    if api.has_capability("characters.drop_held") and characters.drop_held then
        pcall(characters.drop_held, runtime_target(target), cut.side)
    end
    stump_bleed[target] = cfg.sever_bleed
    return true
end

-- The broken-bone bits ExCamera reads ("injuries.broken"), sent when they change.""")
sub(M, """    local blunt = injuries.blunt(hit, weapon_of(hit.weapon_id))
""", """    local blunt = injuries.blunt(hit, weapon_of(hit.weapon_id))
    if not blunt and (hit.health_damage or 0) >= cfg.sever_at and sever(target, hit.part) then
        if hit.is_player then
            say("Your " .. readable(hit.part) .. " is cut off.")
            save_player()
        end
    end
""")
# Bleeding from a stump: the game's own damage applier, a little every tick.
sub(M, """    announce(injuries.tick(now, dt))""", """    announce(injuries.tick(now, dt))
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
    end""")
# Saved: the player's severed bits; cut again at the next session.
sub(M, """    save_data.set(injuries.encode() .. (scar > 0 and string.format("|S%.3f", scar) or ""))""",
    """    save_data.set(injuries.encode() .. (scar > 0 and string.format("|S%.3f", scar) or "") ..
                  ((severed.player or 0) ~= 0 and string.format("|X%d", severed.player) or ""))""")
sub(M, """        if scars.player then send_scar("player") end""", """        if scars.player then send_scar("player") end
        local saved_bits = tonumber((api.has_capability("storage.save") and save_data and save_data.get() or ""):match("|X(%d+)"))
        severed, stump_bleed = {}, {}
        if saved_bits then
            for hit_part, cut in pairs(injuries.SEVER) do
                if hit_part == cut.part and saved_bits & (1 << cut.bit) ~= 0 then sever("player", hit_part) end
            end
            stump_bleed = {}
        end""")
sub("manifest.toml", """            "characters.drop_held", "characters.soil_worn"]""", """            "characters.drop_held", "characters.soil_worn", "characters.sever"]
# characters.sever is requested (section 6): a hard cut takes an arm off at the shoulder or elbow.""")
print("ok")
