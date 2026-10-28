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
-- U+200F/U+200E so bidi keeps working); unknown entities and stray HTML
-- tags are stripped; `{\...}` ASS override blocks and `\h` are untouched.
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
}

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

local function decode_entities(text)
    text = text:gsub("&#x([%x]+);", function(hex)
        local cp = tonumber(hex, 16)
        if cp and cp > 0 and cp < 0x110000 then return utf8_encode(cp) end
        return ""  -- out-of-range codepoint: rendering garbage
    end)
    text = text:gsub("&#(%d+);", function(dec)
        local cp = tonumber(dec)
        if cp and cp > 0 and cp < 0x110000 then return utf8_encode(cp) end
        return ""
    end)
    text = text:gsub("&([%a%d]+);", function(name)
        return NAMED_ENTITIES[name]  -- unknown names fall through
    end)
    -- whatever the table did not know would render as garbage anyway
    text = text:gsub("&[%a%d]+;", "")
    return text
end

local function strip_html_tags(text)
    -- Any `<name ...>...</name>` construct is stray HTML: libass shows it
    -- verbatim. Dialogue like "a < b and c > d" keeps its space after the
    -- angle bracket and never matches; `{\...}` ASS blocks contain no `<>`.
    return (text:gsub("</?%a+[^>\r\n]*>", ""))
end

local function sanitize_content(content)
    return strip_html_tags(decode_entities(content))
end

local function looks_unsanitized(text)
    if type(text) ~= "string" then return false end
    if text:find("&%a+;") then return true end
    if text:find("&#%d+;") then return true end
    if text:find("&#x%x+;") then return true end
    return text:find("</?%a+[^>\r\n]*>") ~= nil
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

    local cleaned = sanitize_content(content)
    if cleaned == content then
        msg.info("sub_sanitizer: track is already clean")
        return false
    end

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
    decode_entities = decode_entities,
    sanitize_content = sanitize_content,
    looks_unsanitized = looks_unsanitized,
    sanitize_track = sanitize_track,
    state = state,
    options = o,
}