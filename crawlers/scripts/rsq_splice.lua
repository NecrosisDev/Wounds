-- Splices this mod's clips (clips.bin) into the installed humanoid.rsq: the new clip names go after the
-- file's own, the first set (Default, the root every other set inherits from) gets the new tracks, and
-- every other set gets an empty entry (an i32 0) for each. The same splice as tools/splice.py.
local M = {}

local TAG_CLIPS, BONE_STRIDE = 0x3DAB, 20

-- clips.bin -> names (24-byte records), tracks (encoded), count, and the clip names.
function M.read_clips(blob)
    local count, p = string.unpack("<I4", blob, 1)
    local names, tracks, list = {}, {}, {}
    for i = 1, count do
        names[i] = blob:sub(p, p + 23)
        list[i] = (names[i]:sub(1, 16):gsub("%z.*", ""))
        p = p + 24
        local n = string.unpack("<i4", blob, p)
        local size = 8 + n * 4 + n * 12 + n * 18 * BONE_STRIDE
        tracks[i] = blob:sub(p, p + size - 1)
        p = p + size
    end
    return {count = count, names = table.concat(names), tracks = table.concat(tracks), list = list}
end

-- The spliced file, and the motion index of the first new clip (the file's own clip count), or nil and why.
function M.splice(data, clips)
    local out, q = {}, 1
    local first = nil
    while q <= #data do
        local tag, size = string.unpack("<I4I4", data, q)
        local body = data:sub(q + 8, q + 7 + size)
        if tag == TAG_CLIPS then
            local nb, nc, ns = string.unpack("<I4I4I4", body, 1)
            if nb ~= 18 then return nil, "the skeleton has " .. nb .. " bones, not 18" end
            first = nc
            local r = 13 + nc * 24
            local parts = {string.pack("<I4I4I4", nb, nc + clips.count, ns), body:sub(13, r - 1), clips.names}
            local empty = string.pack("<i4", 0):rep(clips.count)
            for s = 1, ns do
                local start = r
                r = r + 32
                for _ = 1, nc do
                    local n = string.unpack("<i4", body, r)
                    r = r + (n < 1 and 4 or 8 + n * 4 + n * 12 + n * nb * BONE_STRIDE)
                end
                parts[#parts + 1] = body:sub(start, r - 1)
                parts[#parts + 1] = s == 1 and clips.tracks or empty
            end
            if r ~= #body + 1 then return nil, "the clip chunk did not read to its end" end
            body = table.concat(parts)
        end
        out[#out + 1] = string.pack("<I4I4", tag, #body) .. body
        q = q + 8 + size
    end
    if not first then
        -- What arrived, for the log: the size, the first bytes and the chunks walked.
        return nil, string.format("no clip chunk (%d bytes, %d chunks, starts %s)", #data, #out,
            (data:sub(1, 16):gsub(".", function(c) return string.format("%02x", c:byte()) end)))
    end
    return table.concat(out), first
end

return M
