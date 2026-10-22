-- Load check for Ground Fighters against a stub of the runtime, plus the Lua splice against the Python one.
-- Usage: lua harness.lua <mod folder> <installed humanoid.rsq> <expected spliced rsq>
local root, rsq_path, expected_path = assert(arg[1]), assert(arg[2]), assert(arg[3])
local function read(path) local f = assert(io.open(path, "rb")) local s = f:read("a") f:close() return s end
local installed, expected = read(rsq_path), read(expected_path)

local function new(opts)
    opts = opts or {}
    local s = {logs = {}, handlers = {}, timers = {}, afters = {}, now = 100, served = nil, played = {}, drifted = {}, hurt = {},
               chars = opts.chars or {}}
    local caps = {["events.lifecycle"] = true, timers = true, ["levels.serve"] = true, ["levels.read"] = true,
                  ["assets.read"] = true, ["characters.read"] = true, ["characters.motion"] = not opts.no_motion,
                  ["characters.drift"] = true, ["player.damage"] = true}
    local env = {math = math, string = string, table = table, ipairs = ipairs, pairs = pairs, next = next, pcall = pcall,
                 tonumber = tonumber, tostring = tostring, type = type, error = error, assert = assert}
    env.log = {info = function(m) s.logs[#s.logs + 1] = "info: " .. m end, warn = function(m) s.logs[#s.logs + 1] = "warn: " .. m end}
    env.api = {has_capability = function(n) return caps[n] == true end}
    env.events = {on = function(n, fn) s.handlers[n] = fn end}
    env.timers = {every = function(_, fn) s.timers[#s.timers + 1] = fn return #s.timers end,
                  after = function(_, fn) s.afters[#s.afters + 1] = fn return 1 end,
                  cancel = function(id) s.timers[id] = false end, now = function() return s.now end}
    env.assets = {read = function(path) return read(root .. "/" .. path) end}
    env.levels = {read = function(member, package) assert(member == "humanoid.rsq" and package == "Resource.rpk") return installed end,
                  serve = function(member, bytes, package) s.served = bytes return true end}
    env.characters = {snapshot = function() return {characters = s.chars} end}
    if not opts.no_motion then
        env.characters.play_motion = function(row, name) s.played[#s.played + 1] = row.handle .. ":" .. name return true end
    end
    env.characters.drift = function(row, dir, speed) s.drifted[#s.drifted + 1] = {row.handle, dir, speed} return true end
    env.player = {damage = function(b, h, fall) s.hurt[#s.hurt + 1] = {b, h} return true end}
    local modules = {}
    env.require = function(name)
        if modules[name] == nil then modules[name] = assert(loadfile(root .. "/scripts/" .. name .. ".lua", "t", env))() end
        return modules[name]
    end
    assert(loadfile(root .. "/scripts/main.lua", "t", env))()
    s.fire = function(n, e) return s.handlers[n](e) end
    s.tick = function() s.now = s.now + 0.25 for _, fn in ipairs(s.timers) do if fn then fn() end end end
    s.run_afters = function() local q = s.afters s.afters = {} for _, fn in ipairs(q) do fn() end end
    return s
end

local undead = {{name = "Undead"}}
local function row(handle, x, z, extra)
    local r = {handle = handle, record_id = handle, position = {x, 0, z}, down = true, dead = false, roles = undead}
    for k, v in pairs(extra or {}) do r[k] = v end
    return r
end
local you = {handle = 1, is_player = true, position = {0, 0, 0}}

-- The splice is byte-for-byte the Python one, and served while loading.
local s = new({chars = {you, row(70, 300, 0), row(71, 80, 0), row(72, 80, 0, {roles = {{name = "Bandit"}}}),
                        row(73, 80, 0, {down = false})}})
s.fire("runtime.phase", {phase = "loading"})
assert(s.served == expected, "the Lua splice differs from tools/splice.py")
assert(s.logs[1]:find("motions 48..50"), s.logs[1])

-- Far ones crawl toward you; near ones attack; the living, the standing and the not-undead are left alone.
s.fire("runtime.phase", {phase = "session"})
s.tick()
local played = table.concat(s.played, " ")
assert(played:find("70:Ground Crawl") and played:find("71:Ground Grab"), played)
assert(not played:find("72:") and not played:find("73:"), played)
assert(s.drifted[1][1] == 70 and s.drifted[1][2][1] < -0.99 and s.drifted[1][3] == 41, "drift toward you")
s.run_afters()
assert(#s.hurt == 1 and s.hurt[1][2] == 0.03, "the grab lands")
s.tick()
assert(not table.concat(s.played, " "):find("71:Ground Swipe"), "attacks wait their turn")
for _ = 1, 8 do s.tick() end
assert(table.concat(s.played, " "):find("71:Ground Swipe"), "then a swipe")

-- Without the motion call: the clips are still served, and one warning.
local q = new({no_motion = true, chars = {you, row(71, 80, 0)}})
q.fire("runtime.phase", {phase = "loading"})
q.fire("runtime.phase", {phase = "session"})
q.tick() q.tick()
local warns = 0
for _, l in ipairs(q.logs) do if l:find("^warn") then warns = warns + 1 end end
assert(q.served and warns == 1 and #q.hurt == 0, "served, one warning, no blows")

print("ground fighters harness: all checks passed")
