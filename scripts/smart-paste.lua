-- smart-paste.lua - Robust, layout-agnostic clipboard & drag-and-drop URL loader for mpv
-- Handles all edge cases: leading/trailing whitespace, quotes, partial URLs (watch?v=, youtu.be, shorts/)
-- Intercepts on_load hook so drag-and-drop & relative URLs are automatically normalized
-- Provides continuous OSD visual spinner feedback while yt-dlp resolves the stream

local function trim(s)
    if not s then return nil end
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

local function normalize_url(raw)
    if not raw or type(raw) ~= "string" then return nil end
    local text = trim(raw)
    if not text or text == "" then return nil end

    text = strip_quotes(text)
    if not text or text == "" then return nil end

    -- Already a valid full URL
    if text:find("^https?://") then
        return text
    end

    -- Check if it contains a YouTube watch link (even if mpv or drag-and-drop prepended local working dir)
    local watch_id = text:match("watch%?v=([%w%-_]+.*)")
    if watch_id then
        return "https://www.youtube.com/watch?v=" .. watch_id
    end

    -- Check for shorts
    local shorts_id = text:match("shorts/([%w%-_]+.*)") or text:match("shorts\\([%w%-_]+.*)")
    if shorts_id then
        return "https://www.youtube.com/shorts/" .. shorts_id
    end

    -- Check for youtu.be
    local ytid = text:match("youtu%.be/([%w%-_]+.*)") or text:match("youtu%.be\\([%w%-_]+.*)")
    if ytid then
        return "https://youtu.be/" .. ytid
    end

    -- Check for www.youtube.com or youtube.com without protocol
    local yt_path = text:match("youtube%.com/(.*)") or text:match("youtube%.com\\(.*)")
    if yt_path then
        return "https://www.youtube.com/" .. yt_path
    end

    -- General domain without protocol (e.g., vimeo.com/..., twitch.tv/...)
    if text:find("^[%w%-]+%.%a%a+/.+") and not text:find("^[a-zA-Z]:[/\\]") then
        return "https://" .. text
    end

    return text
end

local function get_clipboard_content()
    local val = mp.get_property("clipboard/text")
    if val and trim(val) ~= "" then return val end
    val = mp.get_property("clipboard")
    if val and trim(val) ~= "" then return val end
    return nil
end

local loading_timer = nil
local loading_start_time = nil
local current_loading_url = nil
local spinner_frames = {"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}
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

-- Intercept on_load hook (priority 10, before ytdl_hook at priority 50)
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
