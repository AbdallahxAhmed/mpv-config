-- sub_sanitizer.lua — repairs subtitles that render HTML entities as text.
--
-- 2026-10-28 report: Arabic subs (embedded MKV tracks and external files)
-- shipped with literal `&rlm;`, `&lrm;`, `&nbsp;` and broken raw tags, and
-- libass renders those verbatim: `&rlm;شيئاً أخيراً؟` shows the entity.
--
-- How it works: sub-text is observed; the first rendered line that still
-- contains entity-like text trips a one-shot sanitize of the WHOLE track.
-- External tracks are read directly; embedded tracks are extracted with
-- ffmpeg (same contract the autosubsync script uses), cleaned, written to
-- a new file, and selected with sub-add — the original track stays
-- available. Entities decode to their real Unicode (RTL marks survive as
-- U+200F/U+200E so bidi keeps working), case-insensitively, through double
-- encoding (`&amp;rlm;`) and a missing ";" on common names; unknown `&x;`
-- entities and stray tags are stripped. Only subtitle text is touched: SRT
-- cue text (keeping the <i> <b> <u> <s> <font> tags mpv renders) and the Text
-- field of ASS Dialogue lines outside `{\...}` blocks; `\h` stays.
--
-- Options (script-opts/sub_sanitizer.conf):
--   enabled=yes            set to no to disable the automatic pass
--   save_next_to_video=no  write `<video>.sanitized.<ext>` next to the
--                          video and reuse it, instead of a temp file
--   remove_original=no     unload the original track after the swap
--
-- The `sub-sanitize` script message force-processes the current track;
-- it exists so the pass is verifiable headless (and scriptable).

local msg = require 'mp.msg'
local options = require 'mp.options'
local utils = require 'mp.utils'

local o = {
    enabled = true,
    save_next_to_video = false,
    remove_original = false,
}
options.read_options(o, "sub_sanitizer")

local state = { processed = {} }

-- Decode to real characters, never delete the marks: `&rlm;` is a bidi
-- control the author wanted (U+200F), so it becomes the actual codepoint.
-- Names are matched case-insensitively (`&RLM;`, `&Nbsp;` occur in the wild).
local NAMED_ENTITIES = {
    rlm = "\226\128\143",   -- U+200F RIGHT-TO-LEFT MARK
    lrm = "\226\128\142",   -- U+200E LEFT-TO-RIGHT MARK
    nbsp = "\194\160",      -- U+00A0 NO-BREAK SPACE
    zwj = "\226\128\141",   -- U+200D ZERO WIDTH JOINER
    zwnj = "\226\128\140",  -- U+200C ZERO WIDTH NON-JOINER
    amp = "&",
    quot = '"',
    apos = "'",
    lt = "<",
    gt = ">",
    hellip = "\226\128\166", -- …
    ndash = "\226\128\147",  -- –
    mdash = "\226\128\148",  -- —
    laquo = "\194\171",      -- «
    raquo = "\194\187",      -- »
    lsquo = "\226\128\152", rsquo = "\226\128\153",
    ldquo = "\226\128\156", rdquo = "\226\128\157",
}

-- Broken converters drop the closing ";" of these; elsewhere a bare "&name"
-- is ordinary text ("R&D", "AT&T") and is left alone.
local SEMICOLON_OPTIONAL = {
    nbsp = true, rlm = true, lrm = true, amp = true, lt = true, gt = true, quot = true,
}

-- SRT tags mpv itself renders; anything else is stray markup. libass shows
-- every <tag> in ASS text verbatim, so ASS keeps none.
local SRT_TAGS = { i = true, b = true, u = true, s = true, font = true }

-- mpv's LuaJIT lacks the utf8 library; emit the byte sequence directly.
local function utf8_encode(cp)
    if cp < 0x80 then
        return string.char(cp)
    elseif cp < 0x800 then
        return string.char(192 + math.floor(cp / 64), 128 + (cp % 64))
    elseif cp < 0x10000 then
        return string.char(
            224 + math.floor(cp / 4096),
            128 + (math.floor(cp / 64) % 64),
            128 + (cp % 64))
    end
    return string.char(
        240 + math.floor(cp / 262144),
        128 + (math.floor(cp / 4096) % 64),
        128 + (math.floor(cp / 64) % 64),
        128 + (cp % 64))
end

local function codepoint(cp)
    if cp and cp > 0 and cp < 0x110000 then return utf8_encode(cp) end
    return ""  -- out-of-range codepoint: rendering garbage
end

local function decode_once(text)
    text = text:gsub("&#[xX](%x+);?", function(hex) return codepoint(tonumber(hex, 16)) end)
    text = text:gsub("&#(%d+);?", function(dec) return codepoint(tonumber(dec)) end)
    text = text:gsub("&(%a%w*)(;?)", function(name, semi)
        local key = name:lower()
        local value = NAMED_ENTITIES[key]
        if value and (semi == ";" or SEMICOLON_OPTIONAL[key]) then return value end
        if semi == ";" then return "" end  -- unknown entity: renders as garbage
        return nil                         -- not an entity: keep the text
    end)
    return text
end

-- Double-encoded entities (`&amp;rlm;`) need a second pass; three is plenty.
local function decode_entities(text)
    for _ = 1, 3 do
        local decoded = decode_once(text)
        if decoded == text then break end
        text = decoded
    end
    return text
end

local function strip_tags(text, keep)
    return (text:gsub("<(/?)(%a[%w%.%-]*)([^>\r\n]*)>", function(_, name)
        if keep and keep[name:lower()] then return nil end
        return ""
    end))
end

local function clean_text(text, keep)
    return strip_tags(decode_entities(text), keep)
end

-- ASS: only the Text field of Dialogue lines, and only outside `{...}`
-- override blocks. Headers, styles, comments and tags stay byte-identical.
local DIALOGUE = "^(Dialogue:" .. string.rep("[^,]*,", 9) .. ")(.*)$"

local function clean_ass_text(text)
    local out, pos = {}, 1
    while true do
        local s, e = text:find("{[^}]*}", pos)
        if not s then
            out[#out + 1] = clean_text(text:sub(pos))
            break
        end
        out[#out + 1] = clean_text(text:sub(pos, s - 1))
        out[#out + 1] = text:sub(s, e)
        pos = e + 1
    end
    return table.concat(out)
end

local function each_line(content, fn)
    local out = {}
    for line in content:gmatch("[^\n]*\n?") do
        if line ~= "" then
            local body, eol = line:match("^(.-)(\r?\n?)$")
            out[#out + 1] = fn(body) .. eol
        end
    end
    return table.concat(out)
end

local function sanitize_content(content, ext)
    if ext == "ass" then
        return each_line(content, function(line)
            local head, text = line:match(DIALOGUE)
            if not head then return line end
            return head .. clean_ass_text(text)
        end)
    end
    -- SRT: cue numbers and timing lines are not text
    return each_line(content, function(line)
        if line:match("^%s*%d+%s*$") or line:find("-->", 1, true) then return line end
        return clean_text(line, SRT_TAGS)
    end)
end

-- sub-text is plain text: mpv already turned the SRT tags it supports into
-- styling, so any tag still visible here is one it shows verbatim.
local function looks_unsanitized(text)
    if type(text) ~= "string" then return false end
    if text:find("&#[xX]%x") or text:find("&#%d") then return true end
    for name, semi in text:gmatch("&(%a%w*)(;?)") do
        local key = name:lower()
        if semi == ";" or (SEMICOLON_OPTIONAL[key] and NAMED_ENTITIES[key]) then return true end
    end
    return text:find("</?%a[%w%.%-]*[^>\r\n]*>") ~= nil
end

-- ── encodings ─────────────────────────────────────────────────────────
-- Entities decode to UTF-8 bytes, so they may only be written into UTF-8.
-- A Windows-1256 file is decoded, cleaned and encoded back to 1256 (it has
-- RLM 0xFE, LRM 0xFD, NBSP 0xA0); UTF-16 is converted to UTF-8; any other
-- legacy encoding is left alone rather than turned into mixed garbage.

-- Windows-1256 bytes 0x80..0xFF -> Unicode (generated from Python's codec).
local CP1256 = {
    0x20AC, 0x067E, 0x201A, 0x0192, 0x201E, 0x2026, 0x2020, 0x2021,
    0x02C6, 0x2030, 0x0679, 0x2039, 0x0152, 0x0686, 0x0698, 0x0688,
    0x06AF, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014,
    0x06A9, 0x2122, 0x0691, 0x203A, 0x0153, 0x200C, 0x200D, 0x06BA,
    0x00A0, 0x060C, 0x00A2, 0x00A3, 0x00A4, 0x00A5, 0x00A6, 0x00A7,
    0x00A8, 0x00A9, 0x06BE, 0x00AB, 0x00AC, 0x00AD, 0x00AE, 0x00AF,
    0x00B0, 0x00B1, 0x00B2, 0x00B3, 0x00B4, 0x00B5, 0x00B6, 0x00B7,
    0x00B8, 0x00B9, 0x061B, 0x00BB, 0x00BC, 0x00BD, 0x00BE, 0x061F,
    0x06C1, 0x0621, 0x0622, 0x0623, 0x0624, 0x0625, 0x0626, 0x0627,
    0x0628, 0x0629, 0x062A, 0x062B, 0x062C, 0x062D, 0x062E, 0x062F,
    0x0630, 0x0631, 0x0632, 0x0633, 0x0634, 0x0635, 0x0636, 0x00D7,
    0x0637, 0x0638, 0x0639, 0x063A, 0x0640, 0x0641, 0x0642, 0x0643,
    0x00E0, 0x0644, 0x00E2, 0x0645, 0x0646, 0x0647, 0x0648, 0x00E7,
    0x00E8, 0x00E9, 0x00EA, 0x00EB, 0x0649, 0x064A, 0x00EE, 0x00EF,
    0x064B, 0x064C, 0x064D, 0x064E, 0x00F4, 0x064F, 0x0650, 0x00F7,
    0x0651, 0x00F9, 0x0652, 0x00FB, 0x00FC, 0x200E, 0x200F, 0x06D2,
}
local CP1256_REVERSE, CP1256_ARABIC = {}, {}
for i, cp in ipairs(CP1256) do
    CP1256_REVERSE[cp] = 0x7F + i
    CP1256_ARABIC[0x7F + i] = cp >= 0x0600 and cp <= 0x06FF
end

local function utf8_codepoints(s)
    local cps = {}
    for ch in s:gmatch("[%z\1-\127\194-\244][\128-\191]*") do
        local b1, n = ch:byte(1), #ch
        local cp
        if n == 1 then cp = b1
        elseif n == 2 then cp = (b1 % 32) * 64 + ch:byte(2) % 64
        elseif n == 3 then cp = (b1 % 16) * 4096 + (ch:byte(2) % 64) * 64 + ch:byte(3) % 64
        else cp = (b1 % 8) * 262144 + (ch:byte(2) % 64) * 4096 + (ch:byte(3) % 64) * 64 + ch:byte(4) % 64 end
        cps[#cps + 1] = cp
    end
    return cps
end

local function is_utf8(s)
    local i, n = 1, #s
    while i <= n do
        local c = s:byte(i)
        local len = c < 0x80 and 1 or (c >= 0xC2 and c <= 0xDF) and 2
            or (c >= 0xE0 and c <= 0xEF) and 3 or (c >= 0xF0 and c <= 0xF4) and 4 or nil
        if not len or i + len - 1 > n then return false end
        for k = i + 1, i + len - 1 do
            local cc = s:byte(k)
            if cc < 0x80 or cc > 0xBF then return false end
        end
        i = i + len
    end
    return true
end

local function utf16_to_utf8(s, big_endian)
    local out, i = {}, 3  -- skip the BOM
    local function unit(k)
        local a, b = s:byte(k, k + 1)
        if not b then return nil end
        return big_endian and a * 256 + b or b * 256 + a
    end
    while i <= #s - 1 do
        local u = unit(i)
        i = i + 2
        if u >= 0xD800 and u <= 0xDBFF then
            local lo = unit(i)
            if lo and lo >= 0xDC00 and lo <= 0xDFFF then
                u = 0x10000 + (u - 0xD800) * 1024 + (lo - 0xDC00)
                i = i + 2
            end
        end
        out[#out + 1] = utf8_encode(u)
    end
    return table.concat(out)
end

local function cp1256_to_utf8(s)
    return (s:gsub("[\128-\255]", function(c) return utf8_encode(CP1256[c:byte() - 0x7F]) end))
end

local function utf8_to_cp1256(s)
    local out = {}
    for _, cp in ipairs(utf8_codepoints(s)) do
        if cp < 0x80 then out[#out + 1] = string.char(cp)
        else out[#out + 1] = string.char(CP1256_REVERSE[cp] or 0x3F) end  -- "?" if not in 1256
    end
    return table.concat(out)
end

local function looks_cp1256(s)
    local high, arabic = 0, 0
    for c in s:gmatch("[\128-\255]") do
        high = high + 1
        if CP1256_ARABIC[c:byte()] then arabic = arabic + 1 end
    end
    return arabic >= 4 and arabic * 2 >= high
end

-- "utf-8", "utf-16le", "utf-16be", "cp1256", or nil for an unknown legacy encoding.
local function detect_encoding(content)
    local b1, b2 = content:byte(1, 2)
    if b1 == 0xFF and b2 == 0xFE then return "utf-16le" end
    if b1 == 0xFE and b2 == 0xFF then return "utf-16be" end
    if is_utf8(content) then return "utf-8" end
    local codepage = (mp.get_property("sub-codepage") or ""):lower()
    if codepage:find("1256", 1, true) or looks_cp1256(content) then return "cp1256" end
    return nil
end

-- Decode to UTF-8 for cleaning; returns text and the function that writes it back.
local function to_utf8(content, encoding)
    if encoding == "utf-16le" then return utf16_to_utf8(content, false), nil end
    if encoding == "utf-16be" then return utf16_to_utf8(content, true), nil end
    if encoding == "cp1256" then return cp1256_to_utf8(content), utf8_to_cp1256 end
    return content, nil
end

-- ── track handling ────────────────────────────────────────────────────

local codec_ext_map = { subrip = "srt", ass = "ass", ssa = "ass" }

local function basename(path)
    return (tostring(path):gsub("\\", "/"):match("([^/]+)$")) or ""
end

local function dirname(path)
    return (tostring(path):gsub("\\", "/"):match("^(.*)/[^/]+$"))
end

local function temp_dir()
    return os.getenv("TEMP") or os.getenv("TMPDIR") or "/tmp"
end

local function read_file(path)
    if not path then return nil end
    local fh = io.open(path, "rb")
    if not fh then return nil end
    local content = fh:read("*a")
    fh:close()
    return content
end

local function write_file(path, content)
    local fh = io.open(path, "wb")
    if not fh then return false end
    fh:write(content)
    fh:close()
    return true
end

local function ffmpeg_candidates()
    if os.getenv("HOME") == nil then
        -- Windows: the installer lands ffmpeg next to mpv
        local prog = os.getenv("ProgramFiles") or "C:/Program Files"
        local appdata = os.getenv("APPDATA") or ""
        return {
            prog .. "/mpv/ffmpeg/bin/ffmpeg.exe",
            appdata .. "/mpv/tools/ffmpeg/ffmpeg.exe",
        }
    end
    return {
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        (os.getenv("HOME") or "") .. "/.local/bin/ffmpeg",
    }
end

local function find_ffmpeg()
    for _, candidate in ipairs(ffmpeg_candidates()) do
        local info = utils.file_info(candidate)
        if info and info.is_file then return candidate end
    end
    return "ffmpeg"  -- last resort: whatever PATH provides
end

local function extract_track(track, ext)
    local video = mp.get_property("path")
    if not video then return nil end
    local raw = utils.join_path(temp_dir(), "sub_sanitizer_extract." .. ext)
    local ret = mp.command_native({
        name = "subprocess",
        playback_only = false,
        capture_stdout = true,
        capture_stderr = true,
        args = {
            find_ffmpeg(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            "-an", "-vn", "-i", video,
            "-map", "0:" .. tostring(track["ff-index"] or track.id),
            "-f", ext, raw,
        },
    })
    if type(ret) ~= "table" or ret.status ~= 0 or not utils.file_info(raw) then
        msg.warn("sub_sanitizer: ffmpeg extraction failed: "
            .. tostring(type(ret) == "table" and ret.stderr or ret))
        return nil
    end
    local content = read_file(raw)
    os.remove(raw)
    return content
end

local function output_path(ext)
    local base = basename(mp.get_property("path") or "subtitles")
    base = base:gsub("%.%a+$", "") .. ".sanitized." .. ext
    if o.save_next_to_video then
        local dir = dirname(mp.get_property("path") or "")
        if dir and dir ~= "" then
            return utils.join_path(dir, base)
        end
    end
    return utils.join_path(temp_dir(), base)
end

local function track_key(track)
    if track.external and track["external-filename"] then
        return "ext:" .. track["external-filename"]
    end
    local path = mp.get_property("path") or ""
    return "embedded:" .. path .. ":" .. tostring(track["ff-index"] or track.id)
end

local function sanitize_track(track)
    if type(track) ~= "table" then return false end
    local key = track_key(track)
    if state.processed[key] then return false end
    -- set before the work: sub-text keeps firing while we extract
    state.processed[key] = true

    local ext = codec_ext_map[track.codec]
    if not ext then
        msg.info("sub_sanitizer: unsupported codec: " .. tostring(track.codec))
        return false
    end

    local content
    if track.external then
        content = read_file(track["external-filename"])
    else
        content = extract_track(track, ext)
    end
    if not content then return false end

    local encoding = detect_encoding(content)
    if not encoding then
        msg.info("sub_sanitizer: unknown legacy text encoding; track left as it is")
        return false
    end
    local text, write_back = to_utf8(content, encoding)
    local cleaned = sanitize_content(text, ext)
    if cleaned == text then
        msg.info("sub_sanitizer: track is already clean")
        return false
    end
    if write_back then cleaned = write_back(cleaned) end

    local out_path = output_path(ext)
    if not write_file(out_path, cleaned) then
        msg.warn("sub_sanitizer: cannot write " .. out_path)
        return false
    end
    msg.info("sub_sanitizer: cleaned track written to " .. out_path)
    mp.commandv("sub-add", out_path, "select", (track.title or "subtitles") .. " [cleaned]")
    if o.remove_original then
        mp.commandv("sub-remove", track.id)
    end
    mp.osd_message("Subtitles sanitized: HTML entities stripped", 2)
    return true
end

local function on_sub_text(_, text)
    if not o.enabled then return end
    if not looks_unsanitized(text) then return end
    sanitize_track(mp.get_property_native("current-tracks/sub"))
end

mp.observe_property("sub-text", "string", on_sub_text)
mp.register_script_message("sub-sanitize", function()
    sanitize_track(mp.get_property_native("current-tracks/sub"))
end)

_G.sub_sanitizer = {
    detect_encoding = detect_encoding,
    is_utf8 = is_utf8,
    decode_entities = decode_entities,
    sanitize_content = sanitize_content,
    looks_unsanitized = looks_unsanitized,
    sanitize_track = sanitize_track,
    state = state,
    options = o,
}
