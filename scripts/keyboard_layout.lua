-- keyboard_layout.lua - hardware scan-code helper for mpv on Windows.
--
-- mpv matches key bindings against the translated character produced by the
-- OS keyboard layout, so with an Arabic layout active, standard letter bindings
-- would not fire.
--
-- On Windows, this script launches the AutoHotkey helper (mpv_arabic_layout.ahk)
-- on startup. The helper captures physical scan codes (H, B, G, etc.) directly
-- when mpv is focused and Arabic is active, giving 1:1 hardware key parity
-- while leaving the system layout and all other apps untouched.
--
-- For cross-platform support (Linux/macOS), the deployer generates native twin
-- bindings in input.conf via mpv_config.layout_twins.

local msg = require 'mp.msg'
local options = require 'mp.options'

local o = {
    enabled = true,
    ahk = true,
    command = "",
    log = "",
}
options.read_options(o, "keyboard_layout")

local SYSTEM_AHK_CANDIDATES = {
    "C:\\Program Files\\mpv\\tools\\AutoHotkey64.exe",
    "C:\\Program Files\\mpv\\autohotkey\\AutoHotkey64.exe",
    "C:\\Program Files\\AutoHotkey\\v2\\AutoHotkey64.exe",
    "C:\\Program Files\\AutoHotkey\\AutoHotkey64.exe",
}

local function file_exists(path)
    local f = io.open(path, "r")
    if f then
        f:close()
        return true
    end
    return false
end

local function resolve_ahk_script()
    return mp.find_config_file("tools/mpv_arabic_layout.ahk")
        or mp.find_config_file("mpv_arabic_layout.ahk")
end

local function resolve_ahk_exe()
    local exe = mp.find_config_file("tools/AutoHotkey64.exe")
        or mp.find_config_file("tools/autohotkey/AutoHotkey64.exe")
        or mp.find_config_file("AutoHotkey64.exe")
    if exe then return exe end

    for _, candidate in ipairs(SYSTEM_AHK_CANDIDATES) do
        if file_exists(candidate) then return candidate end
    end
    return nil
end

local function resolve_ahk()
    local exe = resolve_ahk_exe()
    local script = resolve_ahk_script()
    if exe and script then
        return exe, script
    end
    return nil, nil
end

local function start_guard()
    -- 1. Automatic AutoHotkey scan-code helper for Windows
    -- Runs 100% silently via mpv's native Win32 subprocess API with CREATE_NO_WINDOW
    -- and detached execution, completely eliminating cmd.exe / io.popen console popups.
    if o.ahk and mp.get_property("platform") == "windows" then
        local ahk_exe, ahk_script = resolve_ahk()
        if ahk_exe and ahk_script then
            local cmd = {
                name = "subprocess",
                args = { ahk_exe, ahk_script },
                playback_only = false,
                detach = true,
            }
            if mp.command_native_async then
                mp.command_native_async(cmd, function(success, result, error)
                    if success then
                        msg.info("keyboard layout: AHK helper started asynchronously")
                    else
                        msg.warn("keyboard layout: failed to start AHK helper: " .. tostring(error))
                    end
                end)
            elseif mp.command_native then
                mp.command_native(cmd)
                msg.info("keyboard layout: AHK helper started via native subprocess")
            end
            return true
        end
    end

    -- 2. Legacy guard command check (for safety / backwards compatibility)
    if not o.enabled or o.command == "" then return false end
    if not o.command:find("guard") then
        msg.warn("keyboard layout: the configured command does not look like the guard")
        return false
    end
    msg.info("keyboard layout: legacy python hook retired; using AHK and layout twins")
    return false
end

local started = false
local function init_guard()
    if started then return end
    if start_guard() then
        started = true
    end
end

-- Start immediately on script load so idle mode and initial player window have the layout helper active
init_guard()
mp.register_event("file-loaded", init_guard)

_G.keyboard_layout = { options = o, start = start_guard }
