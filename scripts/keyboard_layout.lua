-- keyboard_layout.lua - keep mpv's window on a latin keyboard layout.
--
-- mpv matches a key binding against the CHARACTER a key produces, so with
-- an Arabic (or any non-latin) layout active the letter bindings never
-- fire. Windows keeps the input layout per input context and mpv's window
-- inherits the layout of whoever started mpv - so a guard puts mpv's own
-- window back on a latin layout and leaves everything else alone.
--
-- The command line comes from script-opts/keyboard_layout.conf (the
-- installer writes it with the right python path), so nothing is guessed
-- at runtime.

local msg = require 'mp.msg'
local options = require 'mp.options'

local o = {
    enabled = true,
    layout = "00000409",
    command = "",
}
options.read_options(o, "keyboard_layout")

local function start_guard()
    if not o.enabled or o.command == "" then return end
    if not o.command:find("mpv_config%.layout_guard") then
        msg.warn("keyboard layout: the configured command does not look like the guard")
        return
    end
    -- start /B detaches: mpv must not wait for the guard.
    local ok, err = pcall(io.popen, 'start /B "" ' .. o.command, "r")
    if not ok then
        msg.warn("keyboard layout: could not start the guard: " .. tostring(err))
        return
    end
    msg.info("keyboard layout: guard started (" .. o.layout .. ")")
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
