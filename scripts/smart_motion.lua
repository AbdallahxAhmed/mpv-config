-- smart_motion.lua — Intelligent Algorithmic Motion Controller for mpv
-- Automatically calibrates video presentation clock, temporal interpolation,
-- and scaling filter based on real-time mathematical cadence analysis
-- (display-fps vs. source fps) and content source (stream vs. local file).

local mp = _G.mp or {}
local msg = mp.msg or { info = function() end, warn = function() end, debug = function() end }
local options = require "mp.options"

local o = {
    enabled = true,
    stream_web_parity = false,
    high_fps_threshold = 50.0,
    cadence_tolerance = 0.005,
    osd_notifications = false,
    settle_delay = 0.25,
    -- Temporal interpolation filter. oversample = point-sample sample-and-hold
    -- (crisp, no ghost trails); linear = temporal cross-fade (softer, trails
    -- moving edges). Both measure identically in mpv's telemetry - the
    -- scaler filter cannot influence presentation timing.
    default_tscale = "oversample",
}
options.read_options(o, "smart_motion")

local state = {
    manual_override = false,
    applying_change = false,
    current_path = nil,
    last_applied = nil,
    settle_timer = nil,
}

-- Checks whether a path is a network stream (YouTube, Twitch, HTTP/HTTPS, etc.)
local function is_network_stream(path)
    if not path or path == "" then return false end
    local p = path:lower()
    return p:match("^https?://") ~= nil
        or p:match("^ytdl://") ~= nil
        or p:match("^edl://") ~= nil
        or p:match("^rtsp://") ~= nil
        or p:match("^rtmp://") ~= nil
        or p:match("^mms://") ~= nil
end

-- Math: Round to nearest integer
local function round(x)
    return math.floor(x + 0.5)
end

-- Core algorithm: evaluates optimal motion profile given display_fps, video_fps, and is_stream
local function evaluate_motion_profile(display_fps, video_fps, is_stream)
    if not o.enabled then
        return nil
    end

    local tscale_filter = o.default_tscale or "linear"

    -- Rule 1: Streaming Protocol (Web Parity Mode)
    if is_stream and o.stream_web_parity then
        return {
            mode = "stream_web_parity",
            video_sync = "audio",
            interpolation = false,
            tscale = tscale_filter,
            reason = "Network stream: native audio clock (matches web browser fluidity, zero buffering jitter)",
        }
    end

    -- Validate framerates
    if not display_fps or display_fps <= 0 or not video_fps or video_fps <= 0 or video_fps > 300 then
        -- Incomplete telemetry: fallback to safe defaults with smooth phase interpolation
        return {
            mode = "safe_fallback",
            video_sync = "display-resample",
            interpolation = true,
            tscale = tscale_filter,
            reason = "Telemetry settling: safe default (display-resample with " .. tscale_filter .. ")",
        }
    end

    -- Rule 2: High Source Framerate (>= 50fps)
    if video_fps >= o.high_fps_threshold then
        return {
            mode = "high_fps_crisp",
            video_sync = "display-resample",
            interpolation = false,
            tscale = tscale_filter,
            reason = string.format("High-FPS (%.1f fps): raw temporal clarity (zero interpolation blur)", video_fps),
        }
    end

    -- Cadence Analysis
    local ratio = display_fps / video_fps
    local nearest_k = round(ratio)
    local cadence_error = math.abs(ratio - nearest_k) / ratio

    -- Rule 3: Integer Multiple Cadence (e.g. 24fps on 144Hz, 24fps on 120Hz, 30fps on 60Hz)
    if cadence_error < o.cadence_tolerance and nearest_k >= 1 then
        return {
            mode = "integer_cadence_lock",
            video_sync = "display-resample",
            interpolation = true,
            tscale = tscale_filter,
            reason = string.format("Integer multiple (%dx refresh at %.1f/%.1f fps): locked vblank alignment with %s", nearest_k, display_fps, video_fps, tscale_filter),
        }
    end

    -- Rule 4: Non-Integer Cadence on High-Refresh Panel (e.g. 25fps on 144Hz, 30fps on 144Hz)
    if display_fps >= 100 then
        return {
            mode = "high_refresh_anti_smear",
            video_sync = "display-resample",
            interpolation = true,
            tscale = tscale_filter,
            reason = string.format("Non-integer cadence (%.2fx at %.1f/%.1f fps): display-resample with %s interpolation", ratio, display_fps, video_fps, tscale_filter),
        }
    end

    -- Rule 5: Standard Refresh (<= 60Hz) with film (24fps on 60Hz)
    return {
        mode = "standard_resample",
        video_sync = "display-resample",
        interpolation = true,
        tscale = tscale_filter,
        reason = string.format("Standard refresh (%.1f Hz / %.1f fps): display-resample with %s", display_fps, video_fps, tscale_filter),
    }
end

local function apply_profile(profile)
    if not profile then return end
    state.applying_change = true

    if profile.video_sync then
        mp.set_property("video-sync", profile.video_sync)
    end
    if profile.interpolation ~= nil then
        mp.set_property_bool("interpolation", profile.interpolation)
    end
    if profile.tscale then
        mp.set_property("tscale", profile.tscale)
    end

    state.last_applied = profile
    state.applying_change = false

    msg.info(string.format("Smart Motion [%s]: %s (sync=%s, interp=%s, tscale=%s)",
        profile.mode, profile.reason, tostring(profile.video_sync), tostring(profile.interpolation), tostring(profile.tscale)))

    if o.osd_notifications then
        mp.osd_message(string.format("Motion: %s", profile.mode), 1.5)
    end
end

local function on_user_tweak(prop_name)
    if state.applying_change then return end
    if not state.manual_override then
        state.manual_override = true
        msg.info(string.format("Smart Motion: user manually altered %s, yielding automation for this video", prop_name))
        if o.osd_notifications then
            mp.osd_message("Smart Motion: Manual Override", 1.5)
        end
    end
end

mp.observe_property("interpolation", "bool", function(_, val)
    if not state.applying_change and state.last_applied and val ~= nil and val ~= state.last_applied.interpolation then
        on_user_tweak("interpolation")
    end
end)

mp.observe_property("tscale", "string", function(_, val)
    if not state.applying_change and state.last_applied and val ~= nil and val ~= state.last_applied.tscale then
        on_user_tweak("tscale")
    end
end)

local function evaluate_and_apply()
    if state.manual_override then return end

    local vid = mp.get_property_native("vid")
    if vid == false or vid == nil then
        return
    end

    local display_fps = mp.get_property_native("display-fps")
    local video_fps = mp.get_property_native("container-fps") or mp.get_property_native("estimated-vf-fps")
    local is_stream = is_network_stream(state.current_path or mp.get_property("path") or "")

    local profile = evaluate_motion_profile(display_fps, video_fps, is_stream)
    apply_profile(profile)
end

local function on_file_loaded()
    local vid = mp.get_property_native("vid")
    if vid == false or vid == nil then
        return
    end

    state.manual_override = false
    state.current_path = mp.get_property("path") or ""

    if state.settle_timer then
        state.settle_timer:kill()
        state.settle_timer = nil
    end

    -- Settle window allows decoder timestamps and estimated-vf-fps to stabilize
    state.settle_timer = mp.add_timeout(o.settle_delay, function()
        state.settle_timer = nil
        evaluate_and_apply()
    end)
end

mp.register_event("file-loaded", on_file_loaded)

-- Adapt when framerate or display refresh rate becomes known / updates
mp.observe_property("container-fps", "native", function(_, val)
    if val and val > 0 and not state.manual_override and state.current_path then
        evaluate_and_apply()
    end
end)

mp.observe_property("estimated-vf-fps", "native", function(_, val)
    if val and val > 0 and not state.manual_override and state.current_path then
        evaluate_and_apply()
    end
end)

mp.observe_property("display-fps", "native", function(_, val)
    if val and val > 0 and not state.manual_override and state.current_path then
        evaluate_and_apply()
    end
end)

local function toggle_engine()
    o.enabled = not o.enabled
    if o.enabled then
        state.manual_override = false
        mp.osd_message("Smart Motion: Enabled (Auto)", 2.0)
        on_file_loaded()
    else
        mp.osd_message("Smart Motion: Disabled (Manual)", 2.0)
    end
    msg.info("Smart Motion enabled = " .. tostring(o.enabled))
end

-- Keyless registration: input.conf owns the key binding (e.g. Ctrl+Alt+m)
mp.add_key_binding(nil, "toggle", toggle_engine)

-- Export for test harness inspection
_G.smart_motion = {
    evaluate_motion_profile = evaluate_motion_profile,
    is_network_stream = is_network_stream,
    apply_profile = apply_profile,
    options = o,
    state = state,
    round = round,
}
