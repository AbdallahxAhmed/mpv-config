-- tests/lua/test_fast_close.lua
-- Unit tests for scripts/fast_close.lua
local total = 0
local function eq(a, b) assert(a == b, tostring(a) .. ' ~= ' .. tostring(b)) end
local function test(name, fn) fn(); total = total + 1; print('ok fast_close: ' .. name) end

local here = debug.getinfo(1, 'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or './') .. '/'
local SCRIPT = here .. '../../scripts/fast_close.lua'

local function create_harness()
    _G.mp = nil
    local h = {props = {}, commands = {}, events = {}, bindings = {}}
    _G.mp = {
        set_property = function(k, v) h.props[k] = v end,
        command = function(cmd) h.commands[#h.commands + 1] = cmd end,
        register_event = function(event_name, fn) h.events[event_name] = fn end,
        add_key_binding = function(key, name, fn)
            if type(name) == 'function' then
                fn = name
                name = key
            end
            h.bindings[name] = fn
        end,
    }
    return h
end

test('registers shutdown event and bindings on linux', function()
    local h = create_harness()
    dofile(SCRIPT)

    -- Should register shutdown event
    eq(type(h.events['shutdown']), 'function')

    -- Should register quit and quit-watch-later bindings
    eq(type(h.bindings['quit']), 'function')
    eq(type(h.bindings['quit-watch-later']), 'function')
end)

test('shutdown event minimizes window', function()
    local h = create_harness()
    dofile(SCRIPT)

    h.events['shutdown']()
    eq(h.props['window-minimized'], 'yes')
end)

test('quit binding minimizes window and issues quit command', function()
    local h = create_harness()
    dofile(SCRIPT)

    h.bindings['quit']()
    eq(h.props['window-minimized'], 'yes')
    eq(h.commands[1], 'quit')
end)

test('quit-watch-later binding minimizes window and issues quit-watch-later command', function()
    local h = create_harness()
    dofile(SCRIPT)

    h.bindings['quit-watch-later']()
    eq(h.props['window-minimized'], 'yes')
    eq(h.commands[1], 'quit-watch-later')
end)

print('All ' .. total .. ' fast_close tests passed.')
