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
    command = "",
    log = "",
}
options.read_options(o, "keyboard_layout")

local function start_guard()
    if not o.enabled or o.command == "" then return end
    if not o.command:find("mpv_config%.layout_guard") then
        msg.warn("keyboard layout: the configured command does not look like the guard")
        return
    end
    -- start /B detaches: mpv must not wait for the guard.
    -- The output is redirected as well: without it the guard keeps mpv's
    -- pipe open and io.popen never returns, which blocks this script's
    -- thread for as long as the guard runs.
    local command = o.command
    local log = o.log
    if log == "" then
        -- mp.get_config_dir does not exist in this mpv (probe: nil), but
        -- the config-dir property is always there.
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

-- The guard is a python process: starting it costs ~120ms, so it
-- waits for the first file instead of delaying the player's start.
local started = false
mp.register_event("file-loaded", function()
    if started then return end
    started = true
    start_guard()
end)

_G.keyboard_layout = { options = o, start = start_guard }
