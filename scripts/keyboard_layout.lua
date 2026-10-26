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
    -- 1. Check mpv configuration directory via mp.find_config_file (works at load time)
    local ahk_script = mp.find_config_file("tools/mpv_arabic_layout.ahk")
        or mp.find_config_file("mpv_arabic_layout.ahk")
    local ahk_exe = mp.find_config_file("tools/AutoHotkey64.exe")
        or mp.find_config_file("tools/autohotkey/AutoHotkey64.exe")
        or mp.find_config_file("AutoHotkey64.exe")

    -- Fallback to config-dir property if available
    if not ahk_exe or not ahk_script then
        local ok_dir, dir = pcall(mp.get_property, "config-dir")
        if ok_dir and dir and dir ~= "" then
            local sep = dir:sub(-1)
            if sep ~= "/" and sep ~= "\\" then dir = dir .. "/" end
            if not ahk_script then
                local s1 = dir .. "tools/mpv_arabic_layout.ahk"
                local s2 = dir .. "mpv_arabic_layout.ahk"
                if file_exists(s1) then ahk_script = s1
                elseif file_exists(s2) then ahk_script = s2 end
            end
            if not ahk_exe then
                local candidates = {
                    dir .. "tools/AutoHotkey64.exe",
                    dir .. "tools/autohotkey/AutoHotkey64.exe",
                    dir .. "AutoHotkey64.exe",
                }
                for _, exe in ipairs(candidates) do
                    if file_exists(exe) then
                        ahk_exe = exe
                        break
                    end
                end
            end
        end
    end

    -- 2. Fallback to system locations if AutoHotkey wasn't in config dir
    if not ahk_exe then
        local candidates = {
            "C:\\Program Files\\mpv\\autohotkey\\AutoHotkey64.exe",
            "C:\\Program Files\\mpv\\tools\\AutoHotkey64.exe",
            "C:\\Program Files\\AutoHotkey\\v2\\AutoHotkey64.exe",
            "C:\\Program Files\\AutoHotkey\\AutoHotkey64.exe",
        }
        for _, exe in ipairs(candidates) do
            if file_exists(exe) then
                ahk_exe = exe
                break
            end
        end
    end

    if ahk_exe and ahk_script then
        return ahk_exe, ahk_script
    end
    return nil, nil
end

local function start_guard()
    -- 1. Automatic AutoHotkey scan-code helper for Windows
    if o.ahk then
        local ahk_exe, ahk_script = resolve_ahk()
        if ahk_exe and ahk_script then
            local cmd = 'start "" /B "' .. ahk_exe:gsub("/", "\\") .. '" "' .. ahk_script:gsub("/", "\\") .. '" >nul 2>&1'
            local ok, p = pcall(io.popen, cmd, "r")
            if ok and p then
                p:close()
                msg.info("keyboard layout: AHK helper started")
                return true
            end
        end
    end

    -- 2. Legacy Python ctypes guard (requires enabled=yes and explicit command)
    if not o.enabled or o.command == "" then return false end
    if not o.command:find("mpv_config%.layout_guard") then
        msg.warn("keyboard layout: the configured command does not look like the guard")
        return false
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
    local ok, p = pcall(io.popen, 'start /B "" ' .. command .. ' >nul 2>&1', "r")
    if not ok or not p then
        msg.warn("keyboard layout: could not start the guard")
        return false
    end
    p:close()
    msg.info("keyboard layout: guard started")
    return true
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
