-- smart-paste.lua - Robust, layout-agnostic clipboard URL loader for mpv
-- Handles all edge cases: leading/trailing whitespace, quotes, partial URLs (watch?v=, youtu.be, etc.)
-- Provides immediate OSD visual feedback upon pressing Ctrl+v / Ctrl+ر

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

local function sanitize_url(raw)
    if not raw or type(raw) ~= "string" then return nil end
    local text = trim(raw)
    if not text or text == "" then return nil end

    text = strip_quotes(text)
    if not text or text == "" then return nil end

    -- Normalize partial URLs
    if text:find("^watch%?v=") then
        text = "https://www.youtube.com/" .. text
    elseif text:find("^youtu%.be/") then
        text = "https://" .. text
    elseif text:find("^youtube%.com/") then
        text = "https://www." .. text
    elseif text:find("^www%.") then
        text = "https://" .. text
    elseif text:find("^[%w%-]+%.%a%a+/.+") and not text:find("^%a+://") and not text:find("^[a-zA-Z]:[/\\]") then
        text = "https://" .. text
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

local pending_url = nil

local function paste_to_open()
    local raw = get_clipboard_content()
    if not raw or trim(raw) == "" then
        mp.osd_message("Clipboard is empty", 2)
        mp.msg.warn("smart-paste: clipboard is empty")
        return
    end

    local url = sanitize_url(raw)
    if not url or url == "" then
        mp.osd_message("Clipboard contains no valid URL or path", 2)
        mp.msg.warn("smart-paste: invalid clipboard content: " .. tostring(raw))
        return
    end

    pending_url = url
    local short = url
    if #short > 60 then
        short = short:sub(1, 57) .. "..."
    end

    mp.osd_message("Loading: " .. short, 4)
    mp.msg.info("smart-paste: loading " .. url)
    mp.commandv("loadfile", url, "replace")
end

local function paste_to_playlist()
    local raw = get_clipboard_content()
    if not raw or trim(raw) == "" then
        mp.osd_message("Clipboard is empty", 2)
        return
    end

    local url = sanitize_url(raw)
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
    pending_url = nil
end)

mp.register_event("end-file", function(event)
    if pending_url and event and event.reason == "error" then
        mp.osd_message("Failed to open link (unavailable or invalid URL)", 5)
        mp.msg.warn("smart-paste: failed to load " .. tostring(pending_url))
        pending_url = nil
    end
end)

mp.add_key_binding(nil, "paste-to-open", paste_to_open)
mp.add_key_binding(nil, "paste-to-playlist", paste_to_playlist)
