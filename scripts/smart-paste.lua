-- smart-paste.lua - Robust, layout-agnostic clipboard & drag-and-drop URL loader for mpv
-- Handles leading/trailing whitespace, quotes and partial URLs (watch?v=, youtu.be, shorts/)
-- Local files are NEVER rewritten into network URLs, even when their own name or
-- parent directory contains "shorts/", "youtube.com" or "watch?v=".
-- Intercepts the on_load hook so drag-and-drop & host-relative URLs are normalized
-- Shows one quiet loading message; no ticking counter, spinner, polling or extra extraction

local utils = require 'mp.utils'

local function trim(s)
    if not s or type(s) ~= "string" then return nil end
    return s:match("^%s*(.-)%s*$")
end

local function strip_quotes(s)
    if not s then return nil end
    if (#s >= 2 and s:sub(1,1) == '"' and s:sub(-1,-1) == '"') or
       (#s >= 2 and s:sub(1,1) == "'" and s:sub(-1,-1) == "'") then
        s = s:sub(2, -2)
        s = trim(s)
    end
    return s
end

-- Any scheme (https://, ytdl://, magnet: style handled separately) is left alone.
local function has_scheme(text)
    return text:find("^%a[%w+.%-]*://") ~= nil
end

local function is_existing_local_file(text)
    local ok, info = pcall(utils.file_info, text)
    return ok and info ~= nil
end

-- A path that is clearly local, or that actually exists on this machine.
local function is_local_path(text)
    if text:find("^[a-zA-Z]:[/\\\\]") or text:find("^[/\\\\]") or text:find("^~")
       or text:find("^%.%.?[/\\\\]") then
        return true
    end
    return is_existing_local_file(text)
end

local function normalize_url(raw)
    if not raw or type(raw) ~= "string" then return nil end
    local text = trim(raw)
    if not text or text == "" then return nil end

    text = strip_quotes(text)
    if not text or text == "" then return nil end

    -- Already a full URL (or another mpv protocol): keep it untouched.
    if has_scheme(text) then
        return text
    end

    -- Real local media wins over any URL-looking substring inside its path.
    if is_local_path(text) then
        return text
    end

    -- Host-relative links, anchored at the start so a directory name cannot match.
    local host, rest = text:match("^([%w%-]+%.[%w%-.]+)/(.*)$")
    if host and rest ~= "" then
        local lower = host:lower()
        if lower == "youtu.be" then
            return "https://youtu.be/" .. rest
        end
        if lower == "youtube.com" or lower:match("%.youtube%.com$") then
            return "https://www.youtube.com/" .. rest
        end
        return "https://" .. text
    end

    -- Bare YouTube fragments copied without a host.
    local watch_id = text:match("^watch%?v=([%w%-_]+.*)$")
    if watch_id then
        return "https://www.youtube.com/watch?v=" .. watch_id
    end

    local shorts_id = text:match("^shorts/([%w%-_]+.*)$")
    if shorts_id then
        return "https://www.youtube.com/shorts/" .. shorts_id
    end

    return text
end

local function get_clipboard_content()
    -- Prompt mpv to update clipboard property if supported
    pcall(function() mp.commandv("update-clipboard", "text") end)

    local val = mp.get_property("clipboard/text")
    if type(val) == "string" and trim(val) ~= "" then return val end

    val = mp.get_property_native("clipboard")
    if type(val) == "string" and trim(val) ~= "" then return val end
    if type(val) == "table" and type(val.text) == "string" and trim(val.text) ~= "" then
        return val.text
    end
    return nil
end

local current_loading_url = nil
local function is_network(url)
    return url:find("^https?://") or url:find("^ytdl://")
end
local function start_loading_indicator(url)
    if current_loading_url == url then return end
    current_loading_url = url
    mp.osd_message(is_network(url) and "Opening link…" or "Opening file…", 60)
end
local function stop_loading_indicator()
    if current_loading_url then mp.osd_message("", 0) end
    current_loading_url = nil
end

-- Normalize before the vendored ytdl hook (priority 10), not alongside it.
-- No extraction or subprocess is performed by this normalization step.
mp.add_hook("on_load", 5, function()
    local path = mp.get_property("stream-open-filename")
    if not path or type(path) ~= "string" then return end

    local normalized = normalize_url(path)
    if normalized and normalized ~= path then
        mp.msg.info("smart-paste: normalized media location")
        mp.set_property("stream-open-filename", normalized)
        path = normalized
    end

    if is_network(path) then
        start_loading_indicator(path)
    elseif current_loading_url ~= path then
        stop_loading_indicator()
    end
end)

local function paste_to_open()
    local raw = get_clipboard_content()
    if not raw or trim(raw) == "" then
        mp.osd_message("Clipboard is empty. Copy a link first.", 3)
        mp.msg.warn("smart-paste: clipboard is empty")
        return
    end

    local url = normalize_url(raw)
    if not url or url == "" then
        mp.osd_message("Clipboard has no link or file path.", 3)
        mp.msg.warn("smart-paste: invalid clipboard content")
        return
    end

    -- Repeated clicks/pastes do not restart the same pending request or its OSD.
    if current_loading_url == url then return end

    start_loading_indicator(url)
    mp.msg.info("smart-paste: opening clipboard media")
    mp.commandv("loadfile", url, "replace")
end

local function paste_to_playlist()
    local raw = get_clipboard_content()
    if not raw or trim(raw) == "" then
        mp.osd_message("Clipboard is empty. Copy a link first.", 3)
        return
    end

    local url = normalize_url(raw)
    if not url or url == "" then
        mp.osd_message("Clipboard has no link or file path.", 3)
        return
    end

    local is_idle = mp.get_property_bool("idle-active", false) or (mp.get_property_number("playlist-count", 0) == 0)
    if is_idle then
        paste_to_open()
    else
        mp.osd_message("Added to playlist.", 2)
        mp.msg.info("smart-paste: appended clipboard media")
        mp.commandv("loadfile", url, "append")
    end
end

mp.register_event("file-loaded", stop_loading_indicator)
mp.register_event("shutdown", stop_loading_indicator)
mp.register_event("end-file", function(event)
    local failed_url = current_loading_url
    stop_loading_indicator()
    if failed_url and event and event.reason == "error" then
        mp.osd_message(is_network(failed_url)
            and "Couldn't open this link. Check the URL or try again."
            or "Couldn't open this file.", 4)
        mp.msg.warn("smart-paste: media could not be opened")
    end
end)

mp.add_key_binding(nil, "paste-to-open", paste_to_open)
mp.add_key_binding(nil, "paste-to-playlist", paste_to_playlist)

