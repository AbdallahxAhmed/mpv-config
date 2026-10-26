-- keyboard_layout.lua - make mpv's letter keys work under ANY layout.
--
-- mpv matches a key binding against the CHARACTER a key produces, so with
-- an Arabic (or any non-latin) layout active the letter bindings never
-- fire.
--
-- Switching mpv's window to another layout does NOT work: Windows'
-- WM_INPUTLANGCHANGEREQUEST toggles to the last active layout of the
-- FOREGROUND thread, so a helper that toggles mpv puts it back on
-- whatever the focused application last used. The guard therefore leaves
-- the layout alone and translates the printable keys instead: while mpv
-- is focused, a key that would produce an Arabic character is swallowed
-- and the US character of the same physical key is injected. The system
-- layout, the taskbar indicator and every other app keep working.
--
-- The command line comes from script-opts/keyboard_layout.conf (the
-- installer writes it with the right python path), so nothing is guessed
-- at runtime.

local msg = require 'mp.msg'
local options = require 'mp.options'

local o = {
    enabled = true,
    ahk = true,
    command = "",
    log = "",
}
options.read_options(o, "keyboard_layout")

local function file_exists(path)
    local f = io.open(path, "r")
    if f then
        f:close()
        return true
    end
    return false
end

local function resolve_ahk()
    local ok_dir, dir = pcall(mp.get_property, "config-dir")
    if not ok_dir or not dir or dir == "" then return nil, nil end
    local sep = dir:sub(-1)
    if sep ~= "/" and sep ~= "\\" then dir = dir .. "/" end

    local ahk_script = dir .. "tools/mpv_arabic_layout.ahk"
    if not file_exists(ahk_script) then
        ahk_script = dir .. "mpv_arabic_layout.ahk"
        if not file_exists(ahk_script) then
            return nil, nil
        end
    end

    local candidates = {
        dir .. "tools/AutoHotkey64.exe",
        dir .. "tools/autohotkey/AutoHotkey64.exe",
        dir .. "AutoHotkey64.exe",
        "C:\\Program Files\\mpv\\autohotkey\\AutoHotkey64.exe",
        "C:\\Program Files\\mpv\\tools\\AutoHotkey64.exe",
        "C:\\Program Files\\AutoHotkey\\v2\\AutoHotkey64.exe",
        "C:\\Program Files\\AutoHotkey\\AutoHotkey64.exe",
    }
    for _, exe in ipairs(candidates) do
        if file_exists(exe) then
            return exe, ahk_script
        end
    end
    return nil, nil
end

local function start_guard()
    -- 1. Automatic AutoHotkey scan-code helper for Windows
    if o.ahk then
        local ahk_exe, ahk_script = resolve_ahk()
        if ahk_exe and ahk_script then
            local cmd = 'start "" /B "' .. ahk_exe:gsub("/", "\\") .. '" "' .. ahk_script:gsub("/", "\\") .. '" >nul 2>&1'
            local ok, err = pcall(io.popen, cmd, "r")
            if ok then
                msg.info("keyboard layout: AHK helper started")
                return
            end
        end
    end

    -- 2. Legacy Python ctypes guard (requires enabled=yes and explicit command)
    if not o.enabled or o.command == "" then return end
    if not o.command:find("mpv_config%.layout_guard") then
        msg.warn("keyboard layout: the configured command does not look like the guard")
        return
    end
    local command = o.command
    local log = o.log
    if log == "" then
        local ok_dir, dir = pcall(mp.get_property, "config-dir")
        if ok_dir and dir and dir ~= "" then
            local sep = dir:sub(-1)
            if sep ~= "/" and sep ~= "\\" then dir = dir .. "/" end
            log = dir .. "keyboard_layout.log"
        end
    end
    if log ~= "" then command = command .. ' --log "' .. log .. '"' end
    local ok, err = pcall(io.popen, 'start /B "" ' .. command .. ' >nul 2>&1', "r")
    if not ok then
        msg.warn("keyboard layout: could not start the guard: " .. tostring(err))
        return
    end
    msg.info("keyboard layout: guard started")
end

local started = false
local function init_guard()
    if started then return end
    started = true
    start_guard()
end

-- Start immediately on script load so idle mode and initial player window have the layout helper active
init_guard()
mp.register_event("file-loaded", init_guard)

_G.keyboard_layout = { options = o, start = start_guard }
