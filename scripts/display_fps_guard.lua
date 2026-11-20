-- display_fps_guard.lua — pin mpv's display rate on Wayland, only for the detected mode.
--
-- On KDE Plasma Wayland mpv's *estimated* refresh rate wanders (126.5 Hz was
-- measured on a 143.98 Hz panel), so display-resample can lock to the wrong
-- cadence. Pinning display-fps-override to the rate the compositor reports
-- avoids that. The old [wayland-144hz-fix] profile pinned a fixed 143.981 on
-- every 140-148 Hz panel and read its own override back through display-fps,
-- so once applied it never let go (2026-11-20 audit, finding 1.3).
--
-- This script:
--   * reads display-fps only while no override is active: that is the rate
--     the compositor reports for the current output;
--   * pins it only on Wayland and only when it matches the mode the deployer
--     detected (script-opts: detected_fps, within tolerance);
--   * unpins and re-checks on every new file and whenever the window moves to
--     another display, so a 60 Hz second monitor is never forced to 143.98;
--   * never touches an override the user set (mpv.conf.user or by hand).

local mp = _G.mp or {}
local msg = mp.msg or { info = function() end, warn = function() end, verbose = function() end }
local options = require "mp.options"

local o = {
    enabled = true,
    -- refresh rate of the mode detected at deploy time; 0 disables the guard
    detected_fps = 0,
    -- kscreen-doctor reports two decimals (143.98) while mpv reports 143.981
    tolerance = 0.01,
    -- delay before re-reading display-fps after the override was cleared
    recheck_delay = 0.25,
}
options.read_options(o, "display_fps_guard")

local state = {
    pinned = nil,        -- rate we set as display-fps-override, nil when not pinned
    user_override = (mp.get_property_number("options/display-fps-override", 0) or 0) > 0,
    displays = nil,      -- last display-names value, to notice a move to another output
    recheck = nil,
    -- every value we wrote: change notifications arrive asynchronously, so the
    -- one for our own pin can land after we already cleared it again
    written = { [0] = true },
}

local function set_override(value)
    state.written[value] = true
    mp.set_property_number("display-fps-override", value)
end

local function is_wayland()
    local current = mp.get_property("current-gpu-context") or ""
    if current:find("wayland") then return true end
    return (mp.get_property("options/gpu-context") or ""):find("wayland") ~= nil
end

local function evaluate()
    if not o.enabled or state.user_override or state.pinned then return end
    if (o.detected_fps or 0) <= 0 or not is_wayland() then return end
    local reported = mp.get_property_number("display-fps")
    if not reported or reported <= 0 then return end
    if math.abs(reported - o.detected_fps) <= o.tolerance then
        state.pinned = reported
        set_override(reported)
        msg.info(string.format("display-fps-override pinned to %.3f (detected mode %.3f)",
            reported, o.detected_fps))
    else
        msg.verbose(string.format("display reports %.3f Hz, detected mode is %.3f: no override",
            reported, o.detected_fps))
    end
end

-- Clear our pin and re-read the real rate shortly after. display-fps may come
-- back with the same value (two identical panels), so the observer alone
-- cannot be relied on to fire.
local function unpin_and_recheck()
    if state.user_override then return end
    if state.pinned then
        state.pinned = nil
        set_override(0)
    end
    if state.recheck then state.recheck:kill() end
    state.recheck = mp.add_timeout(o.recheck_delay, function()
        state.recheck = nil
        evaluate()
    end)
end

mp.observe_property("display-fps", "number", function() evaluate() end)

mp.observe_property("display-names", "native", function(_, names)
    local key = type(names) == "table" and table.concat(names, ",") or tostring(names)
    if state.displays ~= nil and key ~= state.displays then
        unpin_and_recheck()
    end
    state.displays = key
end)

-- An override we did not set means the user took control: hands off.
mp.observe_property("display-fps-override", "number", function(_, value)
    value = value or 0
    if state.user_override or state.written[value] then return end
    if value ~= (state.pinned or 0) then
        state.user_override = true
        state.pinned = nil
        msg.info("display-fps-override changed by hand; the guard stops managing it")
    end
end)

mp.register_event("start-file", unpin_and_recheck)

_G.display_fps_guard = { options = o, state = state, evaluate = evaluate }
