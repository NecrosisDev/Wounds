-- Load check: runs scripts/main.lua against a stub of the runtime (API.md 0.28.0 plus the
-- requested characters.set_limb_strength). Checks the addon's own logic only, not the
-- runtime or the game. Usage: lua harness.lua <mod folder>
local root = assert(arg[1], "mod folder")

local function new(opts)
    opts = opts or {}
    local s = {logs = {}, notes = {}, handlers = {}, timers = {}, afters = {}, now = 100, values = {}, sent = {}, save = opts.save,
               killed = {}, flags = {}, marks = {}, addon_handlers = {}, broken = {}, dropped = {}, burnt = {}, soiled = {}, scarred = {}, severedMarks = {}, cuts = {}}
    local caps = {["events.lifecycle"] = true, timers = true, ["events.combat"] = true, ["items.stats"] = true,
                  ["ui.settings"] = true, ["ui.notify"] = true, ["storage.save"] = true,
                  ["characters.limb_strength"] = not opts.no_runtime,
                  ["player.damage"] = true, ["characters.damage"] = true, ["characters.read"] = true,
                  ["script.flags"] = true, ["characters.marks"] = true}
    local env = {math = math, string = string, table = table, ipairs = ipairs, pairs = pairs, next = next,
                 pcall = pcall, tonumber = tonumber, tostring = tostring, type = type, error = error, assert = assert}
    env.log = {info = function(m) s.logs[#s.logs + 1] = "info: " .. m end,
               warn = function(m) s.logs[#s.logs + 1] = "warn: " .. m end}
    env.api = {has_capability = function(name) return caps[name] == true end}
    env.events = {on = function(name, fn) s.handlers[name] = fn end}
    env.timers = {every = function(_, fn) s.timers[#s.timers + 1] = fn return #s.timers end,
                  after = function(_, fn) s.afters[#s.afters + 1] = fn return 1000 + #s.afters end,
                  cancel = function(id) s.timers[id] = false return true end,
                  now = function() return s.now end}
    env.ui = {notify = function(t) s.notes[#s.notes + 1] = t end}
    env.settings = {
        define = function(title, rows)
            assert(not s.rows and #title <= 32 and #rows >= 1 and #rows <= 32)
            for _, r in ipairs(rows) do
                assert(#r.label <= 40, r.label) assert(not r.help or #r.help <= 160, r.key)
                if r.type == "number" then assert(r.min < r.max and r.step > 0 and (r.max - r.min) / r.step <= 1000, r.key) end
            end
            s.rows = rows
        end,
        get = function(key)
            if s.values[key] ~= nil then return s.values[key] end
            for _, r in ipairs(s.rows) do if r.key == key then return r.default end end
        end,
    }
    env.items = {stats = function(id)
        if id == 1 then return {weapon = {grip = {cut = 0.8, crush = 0.2, point = 0.3}}} end   -- a sword
        if id == 2 then return {weapon = {grip = {cut = 0, crush = 0.9, point = 0}}} end      -- a mace
    end}
    env.save_data = {get = function() return s.save end, set = function(t) assert(#t <= 4096) s.save = t return true end}
    env.script_flags = {
        get = function(name) return s.flags[name] end,
        set = function(name, value)
            assert(#name <= 32 and not name:find("[^%w_]"), "flag name " .. name)
            assert(value == nil or math.type(value) == "integer", "integer")
            s.flags[name] = value return true
        end,
    }
    if not opts.no_addons then
        env.addons = {on = function(name, fn) assert(name == "injuries.heal" or name == "injuries.burn") s.addon_handlers[name] = fn return true end}
    end
    env.player = {damage = function(b, h, fall) s.killed.player = {b, h, fall} return true end}
    env.characters_marks = true
    env.characters = {set_mark = function(target, name, value)
        assert((name == "injuries.mend" or name == "injuries.broken" or name == "injuries.burn" or name == "injuries.burnscar" or name == "injuries.severed") and value >= 0 and value <= 255)
        if name == "injuries.severed" then
            if type(target) == "table" then target = "h" .. target.handle end
            s.severedMarks[target] = value
            return true
        end
        if name == "injuries.burnscar" then
            if type(target) == "table" then target = "h" .. target.handle end
            s.scarred[target] = value ~= 0 and value or nil
            return true
        end
        if name == "injuries.burn" then
            if type(target) == "table" then target = "h" .. target.handle end
            s.burnt[target] = value ~= 0 and value or nil
            return true
        end
        if type(target) == "table" then target = "h" .. target.handle end
        if name == "injuries.broken" then s.broken[target] = value ~= 0 and value or nil return true end
        s.marks[target] = value ~= 0 and value or nil
        return true
    end, snapshot = function()
        local rows = {}
        for _, id in ipairs({7, 8}) do
            rows[#rows + 1] = {record_id = id, handle = id * 10, name = "Bandit", dead = false, damage = function(self, o)
                assert(o.health >= 0 and o.health <= 1 and o.balance >= 0 and o.balance <= 1, "0..1")
                s.killed[self.record_id] = o return true end}
        end
        return {space = "level", truncated = false, characters = rows}
    end}
    if not opts.no_runtime then
        caps["characters.keep_down"] = not opts.no_keep_down
        -- As in the runtime (r51): the staged calls work only inside a timer callback; the
        -- character.hit handler is not one ("only allowed in timer and event callbacks").
        local function staged(name)
            if not s.in_timer then error("characters." .. name .. " is only allowed in timer and event callbacks") end
        end
        env.characters.keep_down = function(target, on)
            staged("keep_down")
            if type(target) == "table" then target = "h" .. target.handle end
            s.downed = s.downed or {}
            s.downed[target] = on
            return true
        end
        caps["characters.sever"] = true
        env.characters.sever = function(target, part)
            staged("sever")
            assert(math.type(part) == "integer" and part >= 1 and part <= 18, "part")
            if type(target) == "table" then target = "h" .. target.handle end
            s.cuts[#s.cuts + 1] = tostring(target) .. ":" .. part
            return true
        end
        caps["characters.soil_worn"] = true
        env.characters.soil_worn = function(target, spec)
            assert(spec.dirt > 0 and spec.wear > 0, "soil amounts")
            s.soiled[#s.soiled + 1] = target
            return true
        end
        caps["characters.drop_held"] = true
        env.characters.drop_held = function(target, side)
            staged("drop_held")
            assert(side == "right" or side == "left", "side")
            if type(target) == "table" then target = "h" .. target.handle end
            s.dropped[#s.dropped + 1] = tostring(target) .. ":" .. side
            return true
        end
        env.characters.set_limb_strength = function(target, part, value)
            if type(target) == "table" then
                assert(math.type(target.handle) == "integer" and target.handle > 0, "handle")
                target = "h" .. target.handle
            end
            assert(target == "player" or math.type(target) == "integer" or target:find("^h%d+$"), "target")
            assert(math.type(part) == "integer" and part >= 1 and part <= 18, "part")
            assert(value >= 0.05 and value <= 1, "value")
            s.sent[target] = s.sent[target] or {}
            s.sent[target][part] = value
            return true
        end
    end
    local modules = {}
    env.require = function(name)
        if modules[name] == nil then
            local chunk = assert(loadfile(root .. "/scripts/" .. name .. ".lua", "t", env))
            modules[name] = chunk()
        end
        return modules[name]
    end
    assert(loadfile(root .. "/scripts/main.lua", "t", env))()
    s.fire = function(name, e) return s.handlers[name](e) end
    s.run_afters = function() local q = s.afters s.afters = {} s.in_timer = true for _, fn in ipairs(q) do fn() end s.in_timer = false end
    s.tick = function(seconds)
        s.in_timer = true
        for _ = 1, seconds do s.now = s.now + 1 for _, fn in ipairs(s.timers) do if fn then fn() end end end
        s.in_timer = false
        s.run_afters()
    end
    return s
end

local function hit(part, damage, weapon, extra)
    local h = {record_id = 7, name = "Bandit", is_player = false, health_damage = damage, balance_damage = 0.3,
               source = "weapon", weapon_id = weapon, part = part}
    for k, v in pairs(extra or {}) do h[k] = v end
    return h
end

-- A mace breaks a shin: the knee goes weak, the foot half as much.
local s = new()
s.fire("runtime.phase", {phase = "session"})
s.fire("character.hit", hit(3, 0.15, 2))
assert(s.sent[7] and s.sent[7][3] < 0.5 and s.sent[7][4] > s.sent[7][3] and s.sent[7][4] < 1, "broken shin")
assert(s.sent[7][2] == nil, "the thigh above is untouched")

-- A sword cut below the threshold does nothing until a second one piles on.
s.fire("character.hit", hit(13, 0.06, 1))
assert(s.sent[7][13] == nil, "light cut")
s.fire("character.hit", hit(13, 0.06, 1))
assert(s.sent[7][13] and s.sent[7][13] > s.sent[7][3], "a cut weakens less than a break")

-- Torso hits, blocked blows and a disabled NPC setting do nothing.
s.fire("character.hit", hit(9, 0.5, 2))
s.fire("character.hit", hit(5, 0.5, 2, {blocked = true}))
assert(s.sent[7][9] == nil and s.sent[7][5] == nil, "torso and blocked")

-- No healing while fighting; after the rest the cut heals fully first.
s.tick(15)
assert(s.sent[7][13] < 1, "still hurt while not rested")
s.tick(20 + 180)
assert(s.sent[7][13] == 1, "the cut healed: " .. tostring(s.sent[7][13]))
assert(s.sent[7][3] < 1, "the break takes longer")
s.tick(600)
assert(s.sent[7][3] == 1 and s.sent[7][4] == 1, "the break healed")

-- The player hears about it and keeps it through a level change and a reload.
s.fire("character.hit", hit(15, 0.2, 2, {is_player = true, record_id = 1}))
assert(s.sent.player and s.sent.player[15] < 0.5, "player arm")
assert(s.notes[#s.notes]:find("left upper arm is broken"), s.notes[#s.notes])
assert(s.save and s.save:find("^15:b:"), tostring(s.save))
s.sent = {}
s.fire("runtime.phase", {phase = "loading"})
s.fire("runtime.phase", {phase = "session"})
assert(s.sent.player and s.sent.player[15] < 0.5, "re-sent after the level change")
local again = new({save = s.save})
again.fire("runtime.phase", {phase = "session"})
assert(again.sent.player and again.sent.player[15] < 0.5, "restored from the save")

-- Switching the setting off returns every limb to full strength.
s.handlers["settings.changed"]({key = "enabled", value = false})
assert(s.sent.player[15] == 1 and s.sent.player[16] == 1, "off restores")

-- Without the runtime call it only warns, once.
local bare = new({no_runtime = true})
bare.fire("runtime.phase", {phase = "session"})
bare.fire("character.hit", hit(3, 0.3, 2))
bare.fire("character.hit", hit(6, 0.3, 2))
local warns = 0
for _, l in ipairs(bare.logs) do if l:find("^warn") then warns = warns + 1 end end
assert(warns == 1, "one warning, got " .. warns)

-- A hard mace blow to the head breaks the neck: the game's damage applier gets a full pool.
local n = new()
n.fire("runtime.phase", {phase = "session"})
n.fire("character.hit", hit(10, 0.1, 2))
n.run_afters()
assert(n.killed[7] == nil, "a light head blow is not fatal")
n.fire("character.hit", hit(10, 0.3, 1))
n.run_afters()
assert(n.killed[7] == nil, "a sword to the head does not break the neck")
n.fire("character.hit", hit(10, 0.3, 2, {record_id = 8}))
assert(n.killed[8] == nil, "staged for a timer callback, not run inside the hit")
n.run_afters()
assert(n.killed[8] and n.killed[8].health == 1 and n.killed[7] == nil, "neck broken: record 8 only")
n.fire("character.hit", hit(10, 0.3, 2, {is_player = true, record_id = 1}))
n.run_afters()
assert(n.killed.player and n.killed.player[2] >= 1, "the player's neck")
assert(n.notes[#n.notes] == "Your neck snaps.", n.notes[#n.notes])

-- Body School's Regenerate: addons.send(..., "injuries.heal", {target, amount}) once a second
-- heals worst first with no rest needed and holds the mend mark until 1.5 s after the last call.
local r = new()
r.fire("runtime.phase", {phase = "session"})
r.fire("character.hit", hit(3, 0.3, 2, {is_player = true, record_id = 1}))    -- severity 1 (break)
r.fire("character.hit", hit(13, 0.07, 1, {is_player = true, record_id = 1}))
r.fire("character.hit", hit(13, 0.07, 1, {is_player = true, record_id = 1}))  -- severity 0.7 (cut)
local heal = assert(r.addon_handlers["injuries.heal"], "registered")
heal({target = "player", amount = 0.4})
assert(r.marks.player == 8, "mend mark while healing")
assert(r.sent.player[3] < 1 and r.sent.player[13] < 1, "both still hurt")
heal({target = "player", amount = 0.4})     -- worst first: the forearm 0.7 -> 0.3 (the shin is at 0.6)
heal({target = "player", amount = 0.6})     -- the shin 0.6 -> 0
heal({target = "player", amount = 0.3})     -- the forearm 0.3 -> 0 (1.7 in all)
assert(r.sent.player[3] == 1 and r.sent.player[13] == 1, "all mended: " .. tostring(r.sent.player[3]) .. " " .. tostring(r.sent.player[13]))
assert(r.notes[#r.notes]:find("has healed"), r.notes[#r.notes])
r.tick(1)
assert(r.marks.player == 8, "mark still held just after")
r.tick(2)
assert(r.marks.player == nil, "mark cleared 1.5 s after the last heal")
-- An NPC by record id; junk messages are ignored.
r.fire("character.hit", hit(6, 0.3, 2))
heal({target = "7", amount = 1}) heal({target = 7, amount = -1}) heal("x")
assert(r.sent[7][6] < 1, "junk ignored")
heal({target = 7, amount = 1})
assert(r.sent[7][6] == 1 and r.marks[7] == 8, "NPC mended")
-- Without the channel nothing breaks.
local quiet = new({no_addons = true})
quiet.fire("runtime.phase", {phase = "session"})
quiet.tick(2)

-- With handles (runtime r37c): one character, not every one sharing its record.
local h = new()
h.fire("runtime.phase", {phase = "session"})
h.fire("character.hit", hit(3, 0.3, 2, {handle = 70}))
assert(h.sent.h70 and h.sent.h70[3] < 0.5 and h.sent[7] == nil, "limb strength by handle")
h.addon_handlers["injuries.heal"]({target = {handle = 70}, amount = 1}, "com.necrosis.bodyschool")
assert(h.sent.h70[3] == 1 and h.marks.h70 == 8, "healed and marked by handle")
h.fire("character.hit", hit(10, 0.3, 2, {handle = 80, record_id = 7}))
h.run_afters()
assert(h.killed[8] and h.killed[7] == nil, "the neck kill finds the row by handle, not the record")

-- Broken bones reach ExCamera as bits, and a badly broken arm drops its weapon; a cut arm does not.
local k = new()
k.fire("runtime.phase", {phase = "session"})
k.fire("character.hit", hit(13, 0.3, 2, {handle = 70}))      -- right forearm, mace: broken, severity 1
assert(k.broken.h70 == 1 << 5, "forearm bit " .. tostring(k.broken.h70))
k.run_afters()                                              -- the drop is staged from a timer
assert(k.dropped[1] == "h70:right", "dropped " .. tostring(k.dropped[1]))
k.fire("character.hit", hit(6, 0.3, 2, {handle = 70}))       -- left shin
assert(k.broken.h70 == (1 << 5) | (1 << 3), "two bones")
k.fire("character.hit", hit(15, 0.18, 1, {handle = 70}))     -- left upper arm, sword: cut, not broken or cut off
assert(#k.dropped == 1 and k.broken.h70 == (1 << 5) | (1 << 3), "a cut drops nothing and sets no bit")
for _ = 1, 3 do k.addon_handlers["injuries.heal"]({target = {handle = 70}, amount = 1}) end
k.tick(1)
assert(k.broken.h70 == nil, "healed bones clear the mark")

-- Burns from the Fire mod: the level rises, reaches ExCamera, soils the clothes, heals with Regenerate and with rest.
local f = new()
f.fire("runtime.phase", {phase = "session"})
local burn = assert(f.addon_handlers["injuries.burn"], "burn topic")
for _ = 1, 5 do burn({target = "player", amount = 0.024}, "com.necrosis.fire") end   -- 0.48
assert(f.burnt.player and f.burnt.player > 110 and f.burnt.player < 135, "burn mark " .. tostring(f.burnt.player))
assert(#f.soiled == 5, "clothes soiled each time")
assert(f.notes[#f.notes] == "Your skin blisters from the fire.", f.notes[#f.notes])
burn({target = {handle = 70}, amount = 2})
assert(f.burnt.h70 == 255, "capped at charred")
f.addon_handlers["injuries.heal"]({target = {handle = 70}, amount = 1})               -- -0.5
assert(f.burnt.h70 and f.burnt.h70 < 140 and f.burnt.h70 > 115, "Regenerate eases burns " .. tostring(f.burnt.h70))
f.tick(20 + 900)
assert(f.burnt.player == nil and f.burnt.h70 == nil, "rest heals burns")
assert(f.scarred.player and f.scarred.player > 60 and f.scarred.player < 80, "a healed burn leaves scar tissue " .. tostring(f.scarred.player))
assert(f.scarred.h70 and f.scarred.h70 > 140, "the charred one scars worse " .. tostring(f.scarred.h70))
assert(f.save and f.save:find("|S0%.2"), "the player's scar is saved: " .. tostring(f.save))
f.fire("runtime.phase", {phase = "loading"})
f.scarred = {}
f.fire("runtime.phase", {phase = "session"})
assert(f.scarred.player, "scar sent again after a level change")
local reloaded = new({save = f.save})
reloaded.fire("runtime.phase", {phase = "session"})
assert(reloaded.scarred.player and reloaded.scarred.player > 60, "scar back after a reload")
burn({target = "x", amount = 1}) burn({target = "player", amount = -1})
assert(f.burnt.player == nil, "junk ignored")

-- A new arena round puts another character on an old row: nothing of the old one carries over.
local rr = new()
rr.fire("runtime.phase", {phase = "session"})
rr.fire("character.hit", hit(13, 0.3, 2, {handle = 70}))                  -- record 7: forearm broken
assert(rr.broken.h70 == 1 << 5, "old body's break")
rr.fire("character.hit", hit(6, 0.3, 2, {handle = 70, record_id = 9}))    -- record 9 on the same row: shin
assert(rr.broken.h70 == 1 << 3, "the new body has only its own break: " .. tostring(rr.broken.h70))

-- Severing: a hard sword cut to a forearm takes it off at the elbow; the hand lets go, the stump bleeds,
-- ExCamera gets the bit; a mace never severs; the player's is saved and cut again next session.
local x = new()
x.fire("runtime.phase", {phase = "session"})
x.fire("character.hit", hit(13, 0.4, 2, {handle = 70}))                 -- mace: no
assert(#x.cuts == 0, "blunt never severs")
x.fire("character.hit", hit(17, 0.4, 1, {handle = 70}))                 -- sword to the right hand: off at the elbow
assert(#x.cuts == 0 and #x.dropped == 0, "nothing staged from inside the hit handler")
x.run_afters()
assert(x.cuts[1] == "h70:13" and x.severedMarks.h70 == 1 << 5, "severed " .. tostring(x.cuts[1]))
assert(x.dropped[#x.dropped] == "h70:right", "the hand let go")
x.tick(5)
assert(x.killed[7] and x.killed[7].health > 0 and x.killed[7].health < 0.05, "the stump bleeds a little each second")
x.fire("character.hit", hit(13, 0.5, 1, {handle = 70}))
assert(#x.cuts == 1, "no second cut at the same joint")
x.fire("character.hit", hit(16, 0.4, 1, {is_player = true, record_id = 1}))
x.run_afters()
assert(x.cuts[2] == "player:16" and x.notes[#x.notes]:find("left forearm is cut off"), x.notes[#x.notes])
assert(x.save:find("|X128"), "saved " .. tostring(x.save))
local y = new({save = x.save})
y.fire("runtime.phase", {phase = "session"})
y.run_afters()
assert(y.cuts[1] == "player:16", "cut again after a reload")

-- Legs: off at the knee, kept on the ground; without keep_down a leg is never cut.
local lg = new()
lg.fire("runtime.phase", {phase = "session"})
lg.fire("character.hit", hit(4, 0.5, 1, {handle = 80}))                 -- a sword to the right foot: off at the knee
lg.run_afters()
assert(lg.cuts[1] == "h80:3" and lg.severedMarks.h80 == 1 << 1 and lg.downed.h80 == true, "leg off, kept down")
assert(#lg.dropped == 0, "a leg drops nothing")
local nk = new({no_keep_down = true})
nk.fire("runtime.phase", {phase = "session"})
nk.fire("character.hit", hit(4, 0.5, 1, {handle = 80}))
assert(#nk.cuts == 0, "no leg cut without keep_down")

print("injuries harness: all checks passed")
