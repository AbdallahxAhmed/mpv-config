-- profile_picker.lua — decides whether the current file is anime, applies the
-- matching mpv profile, and owns the Anime4K shader mode.
--
-- Why a script and not a profile-cond: mpv evaluates a profile-cond whenever
-- a property it references changes, and the condition runs in mpv's internal
-- auto-profile script, where user helpers are not visible. The whole
-- decision would have to be one unreadable expression. A script decides
-- ONCE per file, can log WHY it decided, and is unit testable
-- (tests/lua/test_profile_picker.lua).
--
-- Signals (all offline, no network):
--   group   - a known anime release group in the file name or a path segment
--   series  - the cleaned title is in the user's own series list
--   jpn     - a Japanese audio track (anime keeps the original track)
--   ep      - an episode marker in the title ("- 05", "E05", "S01E02")
--   multi   - a multi-language release tag (MultiSub / Multi Audio)
--   folder  - a path SEGMENT named anime/cartoon (tie breaker only)
--
-- The jpn signal never decides on its own: Japanese live action has Japanese
-- tracks too. It needs an episode marker or a multi-language tag as well.

local msg = require 'mp.msg'
local options = require 'mp.options'

local o = {
    enabled = true,
    -- score needed before the anime profile is applied
    threshold = 3,
    -- release groups that only ship anime; extend it freely
    groups = "Erai-raws,SubsPlease,Anime Time,Judas,Commie,HorribleSubs,Doki,"
        .. "Vivid,Arid,Anime-Kaizoku,Mysterious,ASW,SubsMind,Anime-Shin,ktos,"
        .. "anime-ko,Dokkoida,Getsuga,Neko-Raws,SweetSub,Raws-4U,Trix,Aergo,"
        .. "Raws-Media,Empersor,Mokke,Beatrice-Raws,Dashtail,Kantai,yoroi,"
        .. "kirakira,Lilith-Raws,Tsukikage,Anime_Gear,Project_Noanime,EMBER,gg",
    -- network streams too: YouTube anime keeps a Japanese audio track, so the
    -- same signals work there
    detect_streams = true,
    -- Apply the anime profile (and with it Anime4K) to network
    -- streams? Off by default: the VL CNN chains cost 18-44
    -- mistimed frames at 1080p, which is exactly the cadence
    -- disturbance a 144Hz panel notices. Ctrl+1..Ctrl+6 still
    -- turn Anime4K on for a stream by hand.
    apply_anime_profile_to_streams = false,
}
options.read_options(o, "profile_picker")

-- ── the Anime4K chains ────────────────────────────────────────────────
-- Kept in sync with deploy/registry.py by tests/test_anime4k_modes.py.
local CHAINS = {
    ["off"] = "",
    ["fast"] = "Anime4K_Clamp_Highlights;Anime4K_Upscale_CNN_x2_S;"
        .. "Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;"
        .. "Anime4K_Upscale_CNN_x2_S",
    ["A"] = "Anime4K_Clamp_Highlights;Anime4K_Restore_CNN_VL;Anime4K_Upscale_CNN_x2_VL;"
        .. "Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;Anime4K_Upscale_CNN_x2_M",
    ["A+A"] = "Anime4K_Clamp_Highlights;Anime4K_Restore_CNN_VL;Anime4K_Upscale_CNN_x2_VL;"
        .. "Anime4K_Restore_CNN_M;Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;"
        .. "Anime4K_Upscale_CNN_x2_M",
    ["B"] = "Anime4K_Clamp_Highlights;Anime4K_Restore_CNN_Soft_VL;Anime4K_Upscale_CNN_x2_VL;"
        .. "Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;Anime4K_Upscale_CNN_x2_M",
    ["B+B"] = "Anime4K_Clamp_Highlights;Anime4K_Restore_CNN_Soft_VL;Anime4K_Upscale_CNN_x2_VL;"
        .. "Anime4K_Restore_CNN_Soft_M;Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;"
        .. "Anime4K_Upscale_CNN_x2_M",
    ["C"] = "Anime4K_Clamp_Highlights;Anime4K_Upscale_Denoise_CNN_x2_VL;"
        .. "Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;Anime4K_Upscale_CNN_x2_M",
    ["C+A"] = "Anime4K_Clamp_Highlights;Anime4K_Upscale_Denoise_CNN_x2_VL;"
        .. "Anime4K_AutoDownscalePre_x2;Anime4K_AutoDownscalePre_x4;Anime4K_Restore_CNN_M;"
        .. "Anime4K_Upscale_CNN_x2_M",
}

local MODE_ORDER = { "A+A", "A", "B", "B+B", "C+A", "fast", "off" }

local MODE_LABELS = {
    ["off"] = "off",
    ["fast"] = "fast (cheap)",
    ["A"] = "A (sharp)",
    ["A+A"] = "A+A (ultra sharp)",
    ["B"] = "B (soft)",
    ["B+B"] = "B+B (ultra soft)",
    ["C"] = "C (denoise)",
    ["C+A"] = "C+A (denoise + sharp)",
}

-- release noise that is not part of a title
local TOKENS = {}
for _, token in ipairs({
    "2160p", "1080p", "1080i", "720p", "480p", "4k", "uhd", "sd", "hd",
    "bdrip", "brrip", "bd", "bluray", "webrip", "web", "hdtv", "dvdrip", "dvd",
    "remux", "hdr", "dv", "sdr", "10bit", "hi10p", "hevc", "x265", "h265",
    "h264", "x264", "avc", "av1", "av01", "aac", "ac3", "eac3", "ddp", "ddp5",
    "flac", "opus", "atmos", "truehd", "dts", "dtshd", "multisub", "multiaudio",
    "dual", "audio", "multi", "subbed", "dubbed", "raw", "nf", "amzn", "cmu",
    "crunchyroll", "batch", "omake", "complete", "uncensored", "remastered",
    "repack", "cr", "hmax", "hdr10", "www", "com", "net", "org", "jp",
}) do
    TOKENS[token] = true
end

local EPISODE_PATTERNS = {
    "%-%s?%d+[%W]",          -- - 05
    "%sE%d+[%W]",            -- E05
    "%sEP%d+[%W]",           -- EP05
    "%sEpisode%s+%d+[%W]",   -- Episode 05
    "%sS%d+E%d+[%W]",        -- S01E05
    "%sS%d+E%d+%sE%d+[%W]",  -- S01E05E12
}

local state = {
    applied = nil,     -- profile currently in effect ("anime"/"live-action")
    detected = nil,    -- what the detector decided for the current file
    manual = nil,      -- "anime"/"live-action": the user's explicit choice
    mode = "A+A",      -- Anime4K mode in effect
    expect = {},       -- chains WE set - the observer must not read them as a user choice
}

-- ── helpers ───────────────────────────────────────────────────────────

local function split_list(value)
    local out = {}
    for item in tostring(value or ""):gmatch("[^,]+") do
        item = item:match("^%s*(.-)%s*$")
        if item ~= "" then out[#out + 1] = item:lower() end
    end
    return out
end

local function basename(path)
    if not path then return "" end
    return (path:gsub("\\", "/"):match("([^/]+)$")) or path
end

local function path_segments(path)
    local out = {}
    if not path then return out end
    for seg in path:gsub("\\", "/"):gsub("^%a:", "/"):gmatch("([^/]+)") do
        out[#out + 1] = seg:lower()
    end
    return out
end

-- Release groups live in "[Group]" blocks; a CRC/hash block never is.
local function candidate_groups(name, segments)
    local out = {}
    for block in name:gmatch("%[(.-)%]") do
        if not block:match("^%x%x%x%x%x%x%x%x$") then
            for word in block:gmatch("[%w%.%_%-]+") do
                out[#out + 1] = word:lower()
            end
        end
    end
    for _, seg in ipairs(segments) do out[#out + 1] = seg end
    return out
end

local function has_known_group(name, segments, groups)
    for _, candidate in ipairs(candidate_groups(name, segments)) do
        for _, known in ipairs(groups) do
            if candidate == known then return candidate end
        end
    end
    return nil
end

local function has_episode_marker(name)
    for _, pattern in ipairs(EPISODE_PATTERNS) do
        if name:match(pattern) then return true end
    end
    return false
end

local function has_multisub(name)
    local lower = name:lower()
    return lower:find("multisub", 1, true) ~= nil
        or lower:find("multi audio", 1, true) ~= nil
        or lower:find("dual audio", 1, true) ~= nil
end

local function has_jpn_audio(tracks)
    for _, track in ipairs(tracks or {}) do
        if track.type == "audio" then
            local lang = (track.lang or ""):lower()
            local title = (track.title or ""):lower()
            if lang == "jpn" or lang == "ja" or lang == "jp" or lang == "japanese"
                or title:find("japanese", 1, true) or title:find("jpn", 1, true)
                or title:find("日本語", 1, true) then
                return true
            end
        end
    end
    return false
end

-- Drop the release noise so what is left can be compared with the user's
-- series list. Words only - no regex escaping to get wrong.
local function clean_title(name)
    local stripped = name:gsub("%b[]", " "):gsub("%b{}", " ")
    local words = {}
    for word in stripped:gmatch("[%w']+") do
        local lowered = word:lower()
        if not TOKENS[lowered] then words[#words + 1] = lowered end
    end
    return table.concat(words, " ")
end

local function series_entries()
    local found = mp.find_config_file and mp.find_config_file("script-opts/anime_series.conf")
    if not found then return {} end
    local file = io.open(found, "r")
    if not file then return {} end
    local out = {}
    for line in file:lines() do
        local entry = line:match("^%s*series%s*=%s*(.-)%s*$")
        if entry and entry ~= "" then out[#out + 1] = entry:lower() end
    end
    file:close()
    return out
end

local function meta_says_anime()
    for _, key in ipairs({ "tags", "genre", "genres" }) do
        local value = mp.get_property_native("metadata/by-key/" .. key)
        local items = {}
        if type(value) == "table" then
            items = value
        elseif type(value) == "string" then
            items = { value }
        end
        for _, item in ipairs(items) do
            local text = tostring(item):lower()
            if text:find("anime", 1, true) or text:find("animation", 1, true) then
                return true
            end
        end
    end
    return false
end

-- ── the decision ──────────────────────────────────────────────────────

-- Pure function: given a path and the audio track list, decide anime or not.
-- Returns the verdict, the score and the reasons (for the log and the tests).
local function classify(path, tracks, cfg)
    cfg = cfg or {}
    local groups = cfg.groups or split_list(o.groups)
    local series = cfg.series or {}
    local threshold = cfg.threshold or o.threshold or 3
    local name = basename(path)
    local segments = path_segments(path)
    local reasons = {}
    local score = 0

    local group = has_known_group(name, segments, groups)
    if group then
        score = score + 4
        reasons[#reasons + 1] = "group:" .. group
    end

    local title = clean_title(name)
    -- A title from your own list is a HINT, not a verdict: the list
    -- changes with every season you finish, so it must never outvote the
    -- signals that keep working (release group, Japanese audio track,
    -- episode marker) - those describe the RELEASE, not the series.
    for _, entry in ipairs(series) do
        local needle = entry:gsub("[%._]", " "):gsub("%s+", " ")
        if needle ~= "" and title:find(needle, 1, true) then
            score = score + 2
            reasons[#reasons + 1] = "series:" .. entry
            break
        end
    end

    local jpn = has_jpn_audio(tracks)
    local ep = has_episode_marker(name)
    local multi = has_multisub(name)
    if jpn then reasons[#reasons + 1] = "jpn-audio" end
    if ep then reasons[#reasons + 1] = "episode" end
    if multi then reasons[#reasons + 1] = "multisub" end

    if jpn and ep then
        score = score + 3
    elseif jpn and multi then
        score = score + 2
    elseif jpn then
        score = score + 1
    else
        if ep then score = score + 1 end
        if multi then score = score + 1 end
    end

    for _, seg in ipairs(segments) do
        if seg == "anime" or seg == "cartoon" then
            score = score + 1
            reasons[#reasons + 1] = "folder:" .. seg
            break
        end
    end

    return { anime = score >= threshold, score = score, reasons = reasons }
end

-- ── the Anime4K mode ──────────────────────────────────────────────────

local function chain_for(mode)
    local chain = CHAINS[mode]
    if chain == nil then return nil end
    if chain == "" then return "" end
    local out = {}
    for shader in (chain .. ";"):gmatch("([^;]*);") do
        if shader ~= "" then out[#out + 1] = "~~/shaders/" .. shader .. ".glsl" end
    end
    return table.concat(out, ";")
end

local function mode_file_path()
    local found = mp.find_config_file and mp.find_config_file("script-opts/anime4k.conf")
    if found and found ~= "" then return found end
    if mp.command_native then
        local expanded = mp.command_native({"expand-path", "~~/script-opts/anime4k.conf"})
        if expanded and expanded ~= "" and not expanded:find("^~~/") then
            return expanded
        end
    end
    -- mp.get_config_dir does not exist in this mpv; use the property.
    local ok_dir, dir = pcall(mp.get_property, "config-dir")
    dir = (ok_dir and dir) or ""
    if dir ~= "" then
        local sep = dir:sub(-1)
        if sep ~= "/" and sep ~= "\\" then dir = dir .. "/" end
        return dir .. "script-opts/anime4k.conf"
    end
    return nil
end

local function read_mode()
    local path = mode_file_path()
    if not path then return nil end
    local file = io.open(path, "r")
    if not file then return nil end
    local mode
    for line in file:lines() do
        local value = line:match("^%s*mode%s*=%s*(.-)%s*$")
        if value and value ~= "" then mode = value end
    end
    file:close()
    return mode
end

local function write_mode(mode)
    local path = mode_file_path()
    if not path then
        msg.warn("cannot persist the Anime4K mode: no config dir")
        return false
    end
    local file = io.open(path, "w")
    if not file then
        msg.warn("cannot persist the Anime4K mode: " .. path)
        return false
    end
    file:write("# Anime4K shader mode used by the anime profile.\n")
    file:write("# one of: off | fast | A | A+A | B | B+B | C | C+A\n")
    file:write("mode=" .. mode .. "\n")
    file:close()
    return true
end

local function mode_of_chain(chain)
    if type(chain) ~= "string" then return nil end
    local normalized = chain:gsub("%s", "")
    for mode, defined in pairs(CHAINS) do
        local candidate = chain_for(mode) or ""
        if candidate:gsub("%s", "") == normalized then return mode end
    end
    return nil
end

local function apply_mode(mode, announce)
    local chain = chain_for(mode)
    if chain == nil then return false end
    state.mode = mode
    state.expect[chain] = true
    mp.set_property("glsl-shaders", chain)
    if announce then
        mp.osd_message("Anime4K: " .. mode .. " - " .. (MODE_LABELS[mode] or mode) .. " (Saved as Default)", 2.5)
    end
    return true
end

-- ── profile handling ──────────────────────────────────────────────────

local function apply_profile(anime)
    local want = anime and "anime" or "live-action"
    if state.applied == want then return false end
    state.applied = want
    mp.commandv("apply-profile", want)
    -- apply-profile sets the profile's own chain synchronously; remember it
    -- so the observer below does not mistake it for a user choice.
    local profile_chain = mp.get_property_native("glsl-shaders")
    if type(profile_chain) == "string" and profile_chain ~= "" then
        state.expect[profile_chain] = true
    end
    -- the profile may carry its own chain; the user's mode wins
    if anime then
        apply_mode(state.mode, false)
        mp.osd_message(string.format("Anime Detected: Anime4K [%s] Active", state.mode), 2.5)
    end
    return true
end

local function decide()
    if not o.enabled then return end
    local path = mp.get_property("path") or ""
    local is_stream = path:find("^https?://") ~= nil or path:find("^ytdl://") ~= nil
    if is_stream and not o.detect_streams then return end
    local apply_here = not is_stream or o.apply_anime_profile_to_streams
    local tracks = mp.get_property_native("track-list") or {}
    local verdict = classify(path, tracks)
    state.detected = verdict.anime
    msg.info(string.format("Profile picker: %s (score %d: %s)",
        verdict.anime and "anime" or "live-action", verdict.score,
        table.concat(verdict.reasons, ", ")))
    if state.manual then return end
    if not apply_here then
        -- a stream keeps the light profile: Anime4K is opt-in there
        apply_profile(false)
        return
    end
    apply_profile(verdict.anime)
end

-- ── wiring ────────────────────────────────────────────────────────────

local M = {}

M.classify = classify
M.clean_title = clean_title
M.has_episode_marker = has_episode_marker
M.has_jpn_audio = has_jpn_audio
M.split_list = split_list
M.state = state
M.CHAINS = CHAINS
M.mode_file_path = mode_file_path

function M.set_mode(mode)
    if CHAINS[mode] == nil then
        mp.osd_message("Unknown Anime4K mode: " .. tostring(mode), 3)
        return false
    end
    apply_mode(mode, true)
    write_mode(mode)
    return true
end
function M.cycle_mode()
    local index = 1
    for i, mode in ipairs(MODE_ORDER) do
        if mode == state.mode then index = i end
    end
    return M.set_mode(MODE_ORDER[(index % #MODE_ORDER) + 1])
end

-- Toggle the manual override: auto -> anime -> live-action -> auto.
function M.toggle_manual()
    local order = { nil, "anime", "live-action" }
    local index = 1
    for i, value in ipairs(order) do
        if value == state.manual then index = i end
    end
    state.manual = order[(index % #order) + 1]
    if state.manual then
        mp.osd_message("Profile: manual " .. state.manual, 2)
        apply_profile(state.manual == "anime")
    else
        mp.osd_message("Profile: auto", 2)
        if state.detected ~= nil then apply_profile(state.detected) end
    end
    return state.manual
end

-- The user changed the chain by hand (Ctrl+1..6): remember that choice.
-- Chains we set ourselves are ignored - otherwise the profile's own chain
-- and an empty base value would look like user choices.
local function on_shaders_changed(_, value)
    if type(value) ~= "string" or value == "" then return end
    if state.expect[value] then
        state.expect[value] = nil
        return
    end
    local mode = mode_of_chain(value)
    if not mode or mode == state.mode then return end
    state.mode = mode
    if write_mode(mode) then
        msg.info("Anime4K mode changed to " .. mode .. " (persisted)")
    end
end

mp.observe_property("glsl-shaders", "string", on_shaders_changed)
mp.register_event("file-loaded", decide)
mp.register_script_message("set-mode", function(mode) return M.set_mode(mode) end)
mp.register_script_message("cycle-mode", function() return M.cycle_mode() end)
mp.register_script_message("toggle-manual", function() return M.toggle_manual() end)
mp.register_script_message("detect-profile", function() decide() end)

state.mode = read_mode() or "A+A"

_G.profile_picker = M
