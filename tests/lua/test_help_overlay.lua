-- help_overlay: the curated cheat sheet
local total = 0
local function eq(a, b) assert(a == b, tostring(a) .. ' ~= ' .. tostring(b)) end
local function test(name, fn) fn(); total = total + 1; print('ok help_overlay: ' .. name) end

local here = debug.getinfo(1, 'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or './') .. '/'
local SCRIPT = here .. '../../scripts/help_overlay.lua'

local function create_harness()
    _G.mp = nil
    local h = {osds = {}, keys = {}, bindings = {}, messages = {}}
    _G.mp = {
        log = function() end,
        msg = {info = function() end, warn = function() end, debug = function() end},
        osd_message = function(text, duration) h.osds[#h.osds + 1] = {text = text, duration = duration} end,
        add_key_binding = function(key, name, fn)
            -- mpv accepts both (key, fn) and (key, name, fn)
            if type(name) == 'function' then
                fn = name
                name = key
            end
            h.keys[#h.keys + 1] = key
            h.bindings[key] = fn
        end,
        register_script_message = function(name, fn) h.messages[name] = fn end,
        get_property = function() return nil end,
        get_property_native = function() return nil end,
        set_property = function() end,
        commandv = function(name, text, duration)
            if name == "show-text" then
                h.osds[#h.osds + 1] = {text = text, duration = (tonumber(duration) or 0) / 1000}
            end
        end,
        add_timeout = function(sec, fn) local t = {fn = fn, kill = function() end}; return t end,
        add_periodic_timer = function() return {kill = function() end} end,
        register_event = function() end,
        observe_property = function() end,
        find_config_file = function() return nil end,
    }
    package.loaded['mp.msg'] = nil
    package.preload['mp.msg'] = function() return {
        info = function() end, warn = function() end, debug = function() end,
    } end
    return h
end

local function load_script()
    local h = create_harness()
    dofile(SCRIPT)
    return h, _G.help_overlay
end

test('the cheat sheet is bound to a layout independent key', function()
    local h = load_script()
    -- "?" and the function keys produce the same character in every layout
    assert(h.bindings["?"], "the ? key must open the cheat sheet")
    assert(h.bindings["F9"], "F9 must open the cheat sheet")
    for _, key in ipairs(h.keys) do
        assert(key:match("^[%?%a]") == nil or key == "?" or key == "F9",
            "a letter key would break under a non-latin layout")
    end
end)

test('the cheat sheet lists the sections a user needs', function()
    local _, help = load_script()
    local text = help.build()
    for _, needle in ipairs({ "PLAYBACK", "VIDEO", "SUBTITLES", "MOUSE", "LAYOUT" }) do
        assert(text:find(needle, 1, true), "missing section: " .. needle)
    end
    for _, needle in ipairs({ "Ctrl+1..Ctrl+6", "Ctrl+g", "cycle", "Ctrl+Shift+" }) do
        assert(text:find(needle, 1, true), "missing entry: " .. needle)
    end
end)

test('the cheat sheet explains the Arabic layout behaviour', function()
    local _, help = load_script()
    local text = help.build()
    assert(text:find("LAYOUT", 1, true))
    assert(text:find("LAYOUT", 1, true))
    -- it must say plainly that Ctrl+letter is layout independent and
    -- Alt+letter is not
    assert(text:find("Ctrl+<letter>", 1, true))
    assert(text:find("Alt+<letter>", 1, true))
end)

test('pressing the key shows the cheat sheet', function()
    local h = load_script()
    h.bindings["?"]()
    eq(1, #h.osds)
    assert(h.osds[1].text:find("PLAYBACK", 1, true))
    assert(h.osds[1].duration >= 5)
end)

print('Help overlay tests passed: ' .. total)
