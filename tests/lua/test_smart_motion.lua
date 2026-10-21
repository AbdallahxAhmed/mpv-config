local total = 0
local function eq(a, b) assert(a == b, tostring(a) .. ' ~= ' .. tostring(b)) end
local function test(name, fn) fn(); total = total + 1; print('ok smart_motion: ' .. name) end

local here = debug.getinfo(1, 'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or './') .. '/'
if not here:match('[/\\]$') and here ~= './' then here = here .. '/' end

local SCRIPT = here .. '../../scripts/smart_motion.lua'

local function create_harness()
    _G.mp = nil
    local h = {props = {}, bindings = {}, keys = {}, osds = {}, timeouts = {}, events = {}, observers = {}}
    _G.mp = {
        log = function() end,
        msg = {info = function() end, warn = function() end, debug = function() end},
        get_property = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        get_property_native = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        get_property_bool = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        set_property = function(k, v) h.props[k] = v end,
        set_property_native = function(k, v) h.props[k] = v end,
        set_property_bool = function(k, v) h.props[k] = v end,
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

test('stream_web_parity: network streams automatically get native audio-sync & no interpolation', function()
    local _, sm = load_script()
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

print(string.format("All %d smart_motion Lua tests passed successfully!", total))
