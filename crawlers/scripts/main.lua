-- Ground Fighters: undead that are down for good (a leg cut off: Injuries keeps them on the ground)
-- fight on from the floor. They drag themselves toward you, then grab and pull or swipe at your legs.
--
-- The three clips are this mod's own data (clips.bin, made by tools/make_clips.py), spliced into the
-- installed humanoid.rsq when the game reads it (levels.serve), so no game file is shipped. Playing them
-- and dragging the body need runtime calls that are requested (RUNTIME-REQUESTS.md section 8):
-- characters.play_motion and characters.drift. Without them the addon only serves the clips and says
-- so once.
local cfg = require("config")
local splice = require("rsq_splice")

local CLIP_NAMES = {crawl = "Ground Crawl", grab = "Ground Grab", swipe = "Ground Swipe"}
local served, warned = false, false

local function warn_once(text)
    if not warned then warned = true log.warn(text) end
end

-- The clips go in before the game reads humanoid.rsq. Whether that read comes after the runtime's
-- loading phase is untraced; the request asks for a guarantee.
local function serve_clips()
    if served then return end
    if not (api.has_capability("levels.serve") and api.has_capability("assets.read") and levels and assets) then
        warn_once("levels.serve or assets.read missing: the ground clips are not served")
        return
    end
    local blob, why = assets.read("scripts/clips.bin")
    if not blob then warn_once("clips.bin: " .. tostring(why)) return end
    local installed, reason = levels.read("humanoid.rsq", "Resource.rpk")
    if not installed then warn_once("humanoid.rsq: " .. tostring(reason)) return end
    local data, first = splice.splice(installed, splice.read_clips(blob))
    if not data then warn_once("humanoid.rsq not spliced: " .. tostring(first)) return end
    served = levels.serve("humanoid.rsq", data, "Resource.rpk") == true
    if served then log.info(string.format("ground clips served as motions %d..%d", first, first + 2)) end
end

local function is_ground_fighter(c)
    if c.is_player or c.dead or not c.down or not c.roles then return false end
    for _, role in ipairs(c.roles) do
        for _, wanted in ipairs(cfg.roles) do
            if role.name == wanted then return true end
        end
    end
    return false
end

local function distance(a, b)
    local dx, dz = b[1] - a[1], b[3] - a[3]
    return math.sqrt(dx * dx + dz * dz), dx, dz
end

local state = {}  -- [handle] = {doing = "crawl"/"grab"/"swipe", next_attack = time, last = "grab"/"swipe"}

local function play(row, what)
    if not (api.has_capability("characters.motion") and characters.play_motion) then
        warn_once("characters.play_motion is not in this runtime: downed undead lie still")
        return false
    end
    local ok, done = pcall(characters.play_motion, row, CLIP_NAMES[what])
    return ok and done == true
end

local function tick()
    if not cfg.enabled or not served or not api.has_capability("characters.read") then return end
    local snap = characters.snapshot({details = true})
    if not snap then return end
    local target = nil -- the player's row (not the global `player`, which deals the damage)
    for _, c in ipairs(snap.characters) do if c.is_player then target = c end end
    if not target or not target.position then return end
    local now = timers.now()
    for _, c in ipairs(snap.characters) do
        if c.handle and c.position and is_ground_fighter(c) then
            local s = state[c.handle] or {doing = nil, next_attack = 0, last = "swipe"}
            state[c.handle] = s
            local dist, dx, dz = distance(c.position, target.position)
            if dist > cfg.sight then
                s.doing = nil
            elseif dist <= cfg.reach then
                if now >= s.next_attack then
                    local what = s.last == "grab" and "swipe" or "grab"
                    if play(c, what) then
                        s.doing, s.last, s.next_attack = what, what, now + cfg.attack_every
                        -- The blow lands at the clip's strike if the player is still in reach.
                        local handle = c.handle
                        timers.after(what == "grab" and 0.5 or 0.25, function()
                            local again = characters.snapshot()
                            if not again then return end
                            local me, you = nil, nil
                            for _, r in ipairs(again.characters) do
                                if r.handle == handle then me = r end
                                if r.is_player then you = r end
                            end
                            if me and you and me.position and you.position and not me.dead and
                                    distance(me.position, you.position) <= cfg.reach + 20 and
                                    api.has_capability("player.damage") and player.damage then
                                if what == "grab" then player.damage(cfg.grab_balance, cfg.grab_health, true)
                                else player.damage(cfg.swipe_balance, cfg.swipe_health, true) end
                            end
                        end)
                    end
                end
            else
                if s.doing ~= "crawl" and play(c, "crawl") then s.doing = "crawl" end
                if s.doing == "crawl" and api.has_capability("characters.drift") and characters.drift then
                    pcall(characters.drift, c, {dx / dist, dz / dist}, cfg.crawl_speed)
                end
            end
        end
    end
end

local timer = nil
events.on("runtime.phase", function(e)
    if e.phase == "loading" then serve_clips() end
    if e.phase == "session" then
        serve_clips()
        state = {}
        if not timer then timer = timers.every(cfg.tick_seconds, tick) end
    elseif timer then
        timers.cancel(timer)
        timer = nil
    end
end)
