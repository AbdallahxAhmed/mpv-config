local total = 0
local function eq(a, b) assert(a == b, tostring(a) .. ' ~= ' .. tostring(b)) end
local function test(name, fn) fn(); total = total + 1; print('ok smart_motion: ' .. name) end

local here = debug.getinfo(1, 'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or './') .. '/'
if not here:match('[/\\]$') and here ~= './' then here = here .. '/' end

local SCRIPT = here .. '../../scripts/smart_motion.lua'

local function create_harness()
    _G.mp = nil
    local h = {props = {}, bindings = {}, keys = {}, osds = {}, timeouts = {}, events = {}, observers = {}, logs = {}, sets = {}}
    _G.mp = {
        log = function() end,
        msg = {info = function(text) h.logs[#h.logs + 1] = text end, warn = function() end, debug = function() end},
        get_property = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        get_property_native = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        get_property_bool = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        set_property = function(k, v) h.props[k] = v; h.sets[#h.sets + 1] = k end,
        set_property_native = function(k, v) h.props[k] = v; h.sets[#h.sets + 1] = k end,
        set_property_bool = function(k, v) h.props[k] = v; h.sets[#h.sets + 1] = k end,
        osd_message = function(text, duration) h.osds[#h.osds + 1] = {text = text, duration = duration} end,
        add_key_binding = function(key, name, fn) h.keys[#h.keys + 1] = key; h.bindings[name] = fn end,
        add_timeout = function(sec, fn)
            local t = {sec = sec, fn = fn, killed = false, kill = function(self) self.killed = true end}
            h.timeouts[#h.timeouts + 1] = t
            return t
        end,
        register_event = function(name, fn) h.events[name] = fn end,
        observe_property = function(name, typ, fn) h.observers[name] = fn end,
        find_config_file = function() return nil end,
        get_opt = function() return nil end,
    }
    package.loaded['mp.options'] = nil
    package.preload['mp.options'] = function() return {
        read_options = function(o) end,
    } end
    return h
end

local function load_script()
    local h = create_harness()
    dofile(SCRIPT)
    return h, _G.smart_motion
end

test('stream_detection: recognizes streaming protocols and rejects local files', function()
    local _, sm = load_script()
    eq(true, sm.is_network_stream("https://www.youtube.com/watch?v=1wPzxBWcn3A"))
    eq(true, sm.is_network_stream("http://example.com/stream.m3u8"))
    eq(true, sm.is_network_stream("ytdl://dQw4w9WgXcQ"))
    eq(true, sm.is_network_stream("edl://https://test.com/v1;https://test.com/v2"))
    eq(false, sm.is_network_stream("C:\\Users\\User\\Videos\\anime.mkv"))
    eq(false, sm.is_network_stream("/home/user/Movies/film.mp4"))
    eq(false, sm.is_network_stream("film.mkv"))
    eq(false, sm.is_network_stream(""))
    eq(false, sm.is_network_stream(nil))
end)

test('default stream sync: network streams maintain display-resample for 144Hz UI', function()
    local _, sm = load_script()
    local p = sm.evaluate_motion_profile(143.981, 25.0, true)
    eq("high_refresh_anti_smear", p.mode)
    eq("display-resample", p.video_sync)
    eq(true, p.interpolation)
    eq("oversample", p.tscale)
end)

test('stream_web_parity: opt-in web parity gets native audio-sync & no interpolation', function()
    local _, sm = load_script()
    sm.options.stream_web_parity = true
    local p = sm.evaluate_motion_profile(143.981, 25.0, true)
    eq("stream_web_parity", p.mode)
    eq("audio", p.video_sync)
    eq(false, p.interpolation)
    eq("oversample", p.tscale)
end)

test('integer_cadence_lock: 24fps on 144Hz panel snaps to locked integer multiple', function()
    local _, sm = load_script()
    local p = sm.evaluate_motion_profile(144.0, 24.0, false)
    eq("integer_cadence_lock", p.mode)
    eq("display-resample", p.video_sync)
    eq(true, p.interpolation)
    eq("oversample", p.tscale)
end)

test('integer_cadence_lock: 23.976fps on 143.981Hz panel snaps cleanly', function()
    local _, sm = load_script()
    local p = sm.evaluate_motion_profile(143.981, 23.976, false)
    eq("integer_cadence_lock", p.mode)
    eq("display-resample", p.video_sync)
    eq(true, p.interpolation)
    eq("oversample", p.tscale)
end)

test('anti_smear: 25fps on 144Hz panel selects oversample to prevent linear ghost drag', function()
    local _, sm = load_script()
    local p = sm.evaluate_motion_profile(143.981, 25.0, false)
    eq("high_refresh_anti_smear", p.mode)
    eq("display-resample", p.video_sync)
    eq(true, p.interpolation)
    eq("oversample", p.tscale)
end)

test('anti_smear: 30fps on 144Hz panel selects oversample', function()
    local _, sm = load_script()
    local p = sm.evaluate_motion_profile(143.981, 30.0, false)
    eq("high_refresh_anti_smear", p.mode)
    eq("display-resample", p.video_sync)
    eq(true, p.interpolation)
    eq("oversample", p.tscale)
end)

test('high_fps_crisp: 60fps video disables interpolation for raw motion clarity', function()
    local _, sm = load_script()
    local p = sm.evaluate_motion_profile(143.981, 60.0, false)
    eq("high_fps_crisp", p.mode)
    eq("display-resample", p.video_sync)
    eq(false, p.interpolation)
    eq("oversample", p.tscale)
end)

test('standard_resample: 24fps on 60Hz display uses display-resample with oversample', function()
    local _, sm = load_script()
    local p = sm.evaluate_motion_profile(60.0, 24.0, false)
    eq("standard_resample", p.mode)
    eq("display-resample", p.video_sync)
    eq(true, p.interpolation)
    eq("oversample", p.tscale)
end)

test('keyless_binding: toggle registered without hardcoded key', function()
    local h, _ = load_script()
    eq('function', type(h.bindings['toggle']))
    eq(nil, h.keys[1])
end)

local function apply_logs(h)
    local n = 0
    for _, line in ipairs(h.logs) do
        if line:match('^Smart Motion %[') then n = n + 1 end
    end
    return n
end

test('dedupe: same profile twice = one log line, no set_property calls', function()
    local h, sm = load_script()
    sm.apply_profile(sm.evaluate_motion_profile(143.981, 23.976, false))
    eq(1, apply_logs(h))
    eq(3, #h.sets)  -- video-sync, interpolation, tscale
    h.sets = {}
    -- A fresh table with the same decision; only the fps-bearing reason differs.
    local again = sm.evaluate_motion_profile(143.98, 23.976, false)
    eq('integer_cadence_lock', again.mode)
    sm.apply_profile(again)
    eq(1, apply_logs(h))
    eq(0, #h.sets)
end)

test('dedupe: a different profile is still applied and logged', function()
    local h, sm = load_script()
    sm.apply_profile(sm.evaluate_motion_profile(143.981, 23.976, false))
    h.sets = {}
    sm.apply_profile(sm.evaluate_motion_profile(143.981, 60.0, false))
    eq('high_fps_crisp', sm.state.last_applied.mode)
    eq(2, apply_logs(h))
    eq(3, #h.sets)
    eq(false, h.props['interpolation'])
end)

test('dedupe: manual override detection still works after a skipped apply', function()
    local h, sm = load_script()
    local p = sm.evaluate_motion_profile(143.981, 23.976, false)
    sm.apply_profile(p)
    sm.apply_profile(sm.evaluate_motion_profile(143.981, 23.976, false))
    h.observers['tscale'](nil, p.tscale)       -- echo of our own value: not a tweak
    h.observers['interpolation'](nil, true)
    eq(false, sm.state.manual_override)
    h.observers['tscale'](nil, 'linear')       -- the user changed it
    eq(true, sm.state.manual_override)
end)

test('dedupe: a new file re-applies even an identical decision', function()
    local h, sm = load_script()
    h.props['vid'] = 1
    h.props['display-fps'] = 143.981
    h.props['container-fps'] = 23.976
    h.props['path'] = '/videos/a.mkv'
    h.events['file-loaded']()
    h.timeouts[#h.timeouts].fn()
    eq(1, apply_logs(h))
    h.sets = {}
    h.props['path'] = '/videos/b.mkv'
    h.events['file-loaded']()
    h.timeouts[#h.timeouts].fn()
    eq(2, apply_logs(h))
    eq(3, #h.sets)
end)

-- ── the user's video-sync wins (2026-11-20 audit, finding 1.4) ─────────

-- props as mpv.conf + mpv.conf.user left them when the script loads
local function load_with(props)
    local h = create_harness()
    for k, v in pairs(props) do h.props[k] = v end
    dofile(SCRIPT)
    return h, _G.smart_motion
end

local function count_sets(h, key)
    local n = 0
    for _, k in ipairs(h.sets) do if k == key then n = n + 1 end end
    return n
end

test('user_sync: video-sync from mpv.conf.user is never overwritten', function()
    for _, configured in ipairs({'audio', 'display-vdrop', 'display-resample-vdrop'}) do
        local h, sm = load_with({['options/video-sync'] = configured, ['video-sync'] = configured})
        sm.apply_profile(sm.evaluate_motion_profile(143.981, 23.976, false))
        eq(0, count_sets(h, 'video-sync'))
        eq(configured, h.props['video-sync'])
        eq(1, count_sets(h, 'tscale'))  -- the rest of the automation still runs
    end
end)

test('user_sync: a hand change during playback holds for later files too', function()
    local h, sm = load_with({['options/video-sync'] = 'display-resample', ['video-sync'] = 'display-resample'})
    sm.apply_profile(sm.evaluate_motion_profile(143.981, 23.976, false))
    h.props['video-sync'] = 'display-vdrop'
    h.observers['video-sync'](nil, 'display-vdrop')
    h.sets = {}
    h.props['vid'] = 1
    h.props['display-fps'] = 143.981
    h.props['container-fps'] = 23.976
    h.props['path'] = '/videos/next.mkv'
    h.events['file-loaded']()
    h.timeouts[#h.timeouts].fn()
    eq(0, count_sets(h, 'video-sync'))
    eq('display-vdrop', h.props['video-sync'])
end)

test('user_sync: switching back to display-resample by hand hands control back', function()
    local h, sm = load_with({['options/video-sync'] = 'audio', ['video-sync'] = 'audio'})
    h.props['video-sync'] = 'display-resample'
    h.observers['video-sync'](nil, 'display-resample')
    sm.options.stream_web_parity = true
    sm.apply_profile(sm.evaluate_motion_profile(143.981, 30.0, true))
    eq('audio', h.props['video-sync'])  -- managed again: stream parity applies
end)

test('user_sync: a profile of the user that changed video-sync is left alone', function()
    local h, sm = load_with({['options/video-sync'] = 'display-resample', ['video-sync'] = 'audio'})
    sm.apply_profile(sm.evaluate_motion_profile(143.981, 23.976, false))
    eq(0, count_sets(h, 'video-sync'))
    eq('audio', h.props['video-sync'])
end)

test('user_sync: the late echo of our own write is not a hand change', function()
    local h, sm = load_with({['options/video-sync'] = 'display-resample', ['video-sync'] = 'display-resample'})
    sm.options.stream_web_parity = true
    sm.apply_profile(sm.evaluate_motion_profile(143.981, 30.0, true))   -- writes audio
    sm.apply_profile(sm.evaluate_motion_profile(143.981, 23.976, false)) -- writes display-resample
    h.observers['video-sync'](nil, 'audio')                              -- arrives late
    eq('display-resample', sm.state.base_sync)
    sm.apply_profile(sm.evaluate_motion_profile(143.981, 30.0, true))
    eq('audio', h.props['video-sync'])
end)

print(string.format("All %d smart_motion Lua tests passed successfully!", total))
