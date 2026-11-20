-- display_fps_guard: pin display-fps-override only for the detected mode, never latch.
local total = 0
local function eq(a, b) assert(a == b, tostring(a) .. ' ~= ' .. tostring(b)) end
local function test(name, fn) fn(); total = total + 1; print('ok display_fps_guard: ' .. name) end

local here = debug.getinfo(1, 'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or './') .. '/'
if not here:match('[/\\]$') and here ~= './' then here = here .. '/' end

local SCRIPT = here .. '../../scripts/display_fps_guard.lua'

local function create_harness(opts, props)
    _G.mp = nil
    local h = {props = props or {}, sets = {}, observers = {}, events = {}, timeouts = {}}
    local function get(k, d) local v = h.props[k]; if v == nil then return d end; return v end
    _G.mp = {
        log = function() end,
        msg = {info = function() end, warn = function() end, verbose = function() end},
        get_property = get,
        get_property_number = get,
        set_property_number = function(k, v) h.props[k] = v; h.sets[#h.sets + 1] = {k, v} end,
        add_timeout = function(sec, fn)
            local t = {sec = sec, fn = fn, kill = function(self) self.killed = true end}
            h.timeouts[#h.timeouts + 1] = t
            return t
        end,
        register_event = function(name, fn) h.events[name] = fn end,
        observe_property = function(name, _, fn) h.observers[name] = fn end,
    }
    package.loaded['mp.options'] = nil
    package.preload['mp.options'] = function() return {
        read_options = function(o) for k, v in pairs(opts or {}) do o[k] = v end end,
    } end
    return h
end

local WAYLAND = {['current-gpu-context'] = 'waylandvk'}

local function load(opts, props)
    local p = {}
    for k, v in pairs(WAYLAND) do p[k] = v end
    for k, v in pairs(props or {}) do p[k] = v end
    local h = create_harness(opts or {detected_fps = 143.98}, p)
    dofile(SCRIPT)
    return h
end

local function report(h, fps)  -- the compositor reports a rate
    h.props['display-fps'] = fps
    h.observers['display-fps']('display-fps', fps)
end

local function run_timeouts(h)
    local pending = h.timeouts
    h.timeouts = {}
    for _, t in ipairs(pending) do if not t.killed then t.fn() end end
end

local function override(h) return h.props['display-fps-override'] or 0 end

test('pins the reported rate when it matches the detected mode', function()
    local h = load()
    report(h, 143.981)
    eq(143.981, override(h))
end)

test('a different panel rate is not forced to 143.981', function()
    for _, fps in ipairs({144.0, 143.856, 120.0, 60.0}) do
        local h = load()
        report(h, fps)
        eq(0, #h.sets)
    end
end)

test('a 144.000 panel detected as 144.00 is pinned to its own rate', function()
    local h = load({detected_fps = 144.0})
    report(h, 144.0)
    eq(144.0, override(h))
end)

test('nothing happens off Wayland or without a detected mode', function()
    local h = load(nil, {['current-gpu-context'] = 'x11vk'})
    report(h, 143.981)
    eq(0, #h.sets)
    h = load({detected_fps = 0})
    report(h, 143.981)
    eq(0, #h.sets)
end)

test('moving to another display clears the pin and re-reads the real rate', function()
    local h = load()
    h.observers['display-names']('display-names', {'DP-2'})
    report(h, 143.981)
    eq(143.981, override(h))
    h.observers['display-names']('display-names', {'HDMI-1'})
    eq(0, override(h))                -- not latched
    report(h, 60.0)                   -- the 60 Hz monitor's own rate
    run_timeouts(h)
    eq(0, override(h))
    h.observers['display-names']('display-names', {'DP-2'})
    report(h, 143.981)
    eq(143.981, override(h))
end)

test('each new file re-checks, even when the rate did not change', function()
    local h = load()
    report(h, 143.981)
    h.events['start-file']()
    eq(0, override(h))
    run_timeouts(h)                   -- display-fps unchanged: no observer event
    eq(143.981, override(h))
end)

test('an override from mpv.conf.user is never touched', function()
    local h = load(nil, {['options/display-fps-override'] = 120.0, ['display-fps-override'] = 120.0})
    report(h, 143.981)
    h.events['start-file']()
    run_timeouts(h)
    h.observers['display-names']('display-names', {'HDMI-1'})
    eq(0, #h.sets)
end)

test('an override changed by hand during playback is respected', function()
    local h = load()
    report(h, 143.981)
    local before = #h.sets
    h.props['display-fps-override'] = 100.0
    h.observers['display-fps-override']('display-fps-override', 100.0)
    h.events['start-file']()
    run_timeouts(h)
    eq(before, #h.sets)
    eq(100.0, override(h))
end)

test('the late notification of our own pin is not mistaken for a hand change', function()
    local h = load()
    report(h, 143.981)
    h.events['start-file']()          -- unpins before the pin's notification arrives
    h.observers['display-fps-override']('display-fps-override', 143.981)
    run_timeouts(h)
    eq(143.981, override(h))          -- still managed: re-pinned
end)

print('Display fps guard tests passed: ' .. total)
