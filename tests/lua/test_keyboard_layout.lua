-- keyboard_layout: the guard that keeps mpv's window on a latin layout
local total = 0
local function eq(a, b) assert(a == b, tostring(a) .. ' ~= ' .. tostring(b)) end
local function test(name, fn) fn(); total = total + 1; print('ok keyboard_layout: ' .. name) end

local here = debug.getinfo(1, 'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or './') .. '/'
local SCRIPT = here .. '../../scripts/keyboard_layout.lua'

local function create_harness()
    _G.mp = nil
    local h = {props = {}, warnings = {}, infos = {}, timeouts = {}, async_commands = {}}
    _G.mp = {
        log = function() end,
        msg = {
            info = function(text) h.infos[#h.infos + 1] = text end,
            warn = function(text) h.warnings[#h.warnings + 1] = text end,
            debug = function() end,
        },
        get_property = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        get_property_native = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        set_property = function(k, v) h.props[k] = v end,
        add_timeout = function(sec, fn)
            local t = {sec = sec, fn = fn, kill = function() end}
            h.timeouts[#h.timeouts + 1] = t
            return t
        end,
        add_periodic_timer = function() return {kill = function() end} end,
        register_event = function() end,
        observe_property = function() end,
        register_script_message = function() end,
        commandv = function() end,
        command_native_async = function(cmd, callback)
            h.async_commands[#h.async_commands + 1] = cmd
            if callback then callback(true, {status = 0}, nil) end
            return 1
        end,
        find_config_file = function() return nil end,
    }
    package.loaded['mp.msg'] = nil
    package.loaded['mp.options'] = nil
    package.preload['mp.msg'] = function() return _G.mp.msg end
    package.preload['mp.options'] = function() return {
        read_options = function(o) end,
    } end
    return h
end

local function load_script()
    local h = create_harness()
    dofile(SCRIPT)
    return h, _G.keyboard_layout
end

test('the script loads and exposes its options', function()
    local h, kl = load_script()
    assert(kl, "the script must expose itself")
    eq(true, kl.options.enabled)
    eq("", kl.options.command)
end)

test('nothing is started when the guard is not configured', function()
    local h, kl = load_script()
    -- no command configured -> no spawn, no error
    kl.start()
    eq(0, #h.warnings)
end)

test('a command that is not the guard is refused', function()
    local h, kl = load_script()
    kl.options.command = "rm -rf /"
    kl.start()
    eq(1, #h.warnings)
    assert(h.warnings[1]:find("guard", 1, true))
end)

test('AHK helper is started via silent native subprocess on Windows', function()
    local h, kl = load_script()
    h.props["platform"] = "windows"
    _G.mp.find_config_file = function(path)
        if path:find("AutoHotkey") then return "C:/Program Files/mpv/tools/AutoHotkey64.exe" end
        if path:find("mpv_arabic_layout.ahk") then return "C:/mpv/tools/mpv_arabic_layout.ahk" end
        return nil
    end
    local started = kl.start()
    eq(true, started)
    eq(1, #h.async_commands)
    eq("subprocess", h.async_commands[1].name)
    eq(true, h.async_commands[1].detach)
    eq(false, h.async_commands[1].playback_only)
    eq("C:/Program Files/mpv/tools/AutoHotkey64.exe", h.async_commands[1].args[1])
    eq("C:/mpv/tools/mpv_arabic_layout.ahk", h.async_commands[1].args[2])
    local has_info = false
    for _, msg in ipairs(h.infos) do
        if msg:find("AHK helper started asynchronously") then has_info = true end
    end
    assert(has_info, "info log must confirm AHK helper started asynchronously")
end)

print('Keyboard layout tests passed: ' .. total)
