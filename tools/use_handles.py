"""Injuries for runtime r37c: one NPC by its live handle (character.hit `handle`), record ids only as a
fallback; the neck kill finds the struck character's row by handle; addons.on handlers get (value, from)."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent


def sub(rel, old, new):
    p = root / rel
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (rel, old[:60], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8")


M = "scripts/main.lua"
# A key per character for the bookkeeping, and the runtime target argument it stands for.
sub(M, "local function send(target)", """-- Bookkeeping keys: "player", "h<handle>" for one live character (character.hit `handle`, runtime
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

local function send(target)""")
sub(M, "        local ok, result = pcall(characters.set_limb_strength, target, part, value)",
    "        local ok, result = pcall(characters.set_limb_strength, runtime_target(target), part, value)")
sub(M, "            if c.record_id == hit.record_id and c.damage and not c.dead then",
    "            local same = hit.handle and c.handle == hit.handle or (not hit.handle and c.record_id == hit.record_id)\n"
    "            if same and c.damage and not c.dead then")
sub(M, "    local target = hit.is_player and \"player\" or hit.record_id\n",
    "    local target = hit.is_player and \"player\" or key_of(hit.handle and {handle = hit.handle} or hit.record_id)\n")
sub(M, "        if can then pcall(characters.set_mark, target, \"injuries.mend\", 0) end",
    "        if can then pcall(characters.set_mark, runtime_target(target), \"injuries.mend\", 0) end")
sub(M, "        pcall(characters.set_mark, target, \"injuries.mend\", math.floor(cfg.mend_fade_seconds))",
    "        pcall(characters.set_mark, runtime_target(target), \"injuries.mend\", math.floor(cfg.mend_fade_seconds))")
sub(M, """-- addons.send("com.necrosis.injuries", "injuries.heal", {target = "player" or record_id, amount = 0..1}):""",
    """-- addons.send("com.necrosis.injuries", "injuries.heal", {target = "player", a record_id or a row/event
-- with a `handle`, amount = 0..1}), delivered as fn(value, from):""")
sub(M, """    local msg = type(a) == "table" and a or b
""", """    local msg = a
""")
sub(M, """    local target = msg.target
    if target ~= "player" and math.type(target) ~= "integer" then return end
""", """    local target = key_of(msg.target)
    if target == nil then return end
""")
sub(M, "local function on_heal(a, b)", "local function on_heal(a, _from)")
print("ok")
