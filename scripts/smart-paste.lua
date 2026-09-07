-- smart-paste.lua - Robust, layout-agnostic clipboard & drag-and-drop URL loader for mpv
-- Handles leading/trailing whitespace, quotes and partial URLs (watch?v=, youtu.be, shorts/)
-- Local files are NEVER rewritten into network URLs, even when their own name or
-- parent directory contains "shorts/", "youtube.com" or "watch?v=".
-- Intercepts the on_load hook so drag-and-drop & host-relative URLs are normalized
-- Provides continuous OSD visual spinner feedback while yt-dlp resolves the stream

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

local loading_timer = nil
local loading_start_time = nil
local current_loading_url = nil
local spinner_frames = {"\u{280B}", "\u{2819}", "\u{2839}", "\u{2838}", "\u{283C}", "\u{2834}", "\u{2826}", "\u{2827}", "\u{2807}", "\u{280F}"}
local spinner_idx = 1

local function start_loading_indicator(url)
    if current_loading_url == url and loading_timer then
        return
    end

    current_loading_url = url
    loading_start_time = mp.get_time()

    local short = url
    if #short > 55 then
        short = short:sub(1, 52) .. "..."
    end

    if loading_timer then
        loading_timer:kill()
        loading_timer = nil
    end

    spinner_idx = 1
    local function update_osd()
        local elapsed = mp.get_time() - (loading_start_time or mp.get_time())
        local frame = spinner_frames[spinner_idx]
        spinner_idx = (spinner_idx % #spinner_frames) + 1
        mp.osd_message(string.format("%s Resolving stream [%.1fs]: %s", frame, elapsed, short), 1)
    end

    loading_timer = mp.add_periodic_timer(0.1, update_osd)
    update_osd()
end

local function stop_loading_indicator(show_done)
    if loading_timer then
        loading_timer:kill()
        loading_timer = nil
    end
    if show_done and loading_start_time then
        local elapsed = mp.get_time() - loading_start_time
        mp.osd_message(string.format("Stream loaded (%.1fs)", elapsed), 2)
    else
        mp.osd_message("", 0)
    end
    current_loading_url = nil
    loading_start_time = nil
end

-- Intercept on_load hook. NOTE: the vendored ytdl_hook also registers on_load
-- at priority 10, so this normalization must stay side-effect free.
mp.add_hook("on_load", 10, function()
    local path = mp.get_property("stream-open-filename")
    if not path or type(path) ~= "string" then return end

    local normalized = normalize_url(path)
    if normalized and normalized ~= path then
        mp.msg.info("smart-paste: rewriting '" .. path .. "' -> '" .. normalized .. "'")
        mp.set_property("stream-open-filename", normalized)
        path = normalized
    end

    if path and (path:find("^https?://") or path:find("^ytdl://")) then
        start_loading_indicator(path)
    end
end)

local function paste_to_open()
    local raw = get_clipboard_content()
    if not raw or trim(raw) == "" then
        mp.osd_message("Clipboard is empty", 2)
        mp.msg.warn("smart-paste: clipboard is empty")
        return
    end

    local url = normalize_url(raw)
    if not url or url == "" then
        mp.osd_message("Clipboard contains no valid URL or path", 2)
        mp.msg.warn("smart-paste: invalid clipboard content: " .. tostring(raw))
        return
    end

    if current_loading_url == url and loading_timer then
        local elapsed = mp.get_time() - (loading_start_time or mp.get_time())
        mp.osd_message(string.format("Already loading stream [%.1fs]... please wait", elapsed), 2)
        return
    end

    start_loading_indicator(url)
    mp.msg.info("smart-paste: loading " .. url)
    mp.commandv("loadfile", url, "replace")
end

local function paste_to_playlist()
    local raw = get_clipboard_content()
    if not raw or trim(raw) == "" then
        mp.osd_message("Clipboard is empty", 2)
        return
    end

    local url = normalize_url(raw)
    if not url or url == "" then
        mp.osd_message("Clipboard contains no valid URL or path", 2)
        return
    end

    local is_idle = mp.get_property_bool("idle-active", false) or (mp.get_property_number("playlist-count", 0) == 0)
    if is_idle then
        paste_to_open()
    else
        local short = url
        if #short > 50 then
            short = short:sub(1, 47) .. "..."
        end
        mp.osd_message("Added to playlist: " .. short, 3)
        mp.msg.info("smart-paste: appending to playlist " .. url)
        mp.commandv("loadfile", url, "append")
    end
end

mp.register_event("file-loaded", function()
    stop_loading_indicator(true)
end)

mp.register_event("end-file", function(event)
    stop_loading_indicator(false)
    if event and event.reason == "error" then
        mp.osd_message("Failed to open link (unavailable or invalid URL)", 4)
        mp.msg.warn("smart-paste: failed to load stream")
    end
end)

mp.add_key_binding(nil, "paste-to-open", paste_to_open)
mp.add_key_binding(nil, "paste-to-playlist", paste_to_playlist)
