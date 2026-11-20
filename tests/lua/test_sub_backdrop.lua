local total=0
local function eq(a,b) assert(a==b,tostring(a)..' ~= '..tostring(b)) end
local function test(name,fn) fn(); total=total+1; print('ok sub_backdrop: '..name) end

-- Regression targets:
--  1) b turns the box on: sub-border-style=background-box, colour untouched
--  2) b again turns it off: back to outline-and-shadow (the default look)
--  3) a fully transparent colour still gives a visible box, and comes back on off
--  4) the binding is registered KEYLESS: keys live in input.conf only

local here = debug.getinfo(1,'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or './') .. '/'
-- here already ends with a separator when match succeeded; normalize both cases
if not here:match('[/\\]$') and here ~= './' then here = here .. '/' end

local DEFAULT = '#B3080808'
local TRANSPARENT = '#00000000'
local SCRIPT = here .. '../../scripts/sub_backdrop.lua'

local function load(color)
    _G.mp = nil
    local h = {props = {['sub-back-color'] = color, ['sub-border-style'] = 'outline-and-shadow'},
               bindings = {}, keys = {}, osds = {}, sets = {}}
    _G.mp = {log = function() end,
        get_property = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        set_property = function(k, v) h.props[k] = v; h.sets[#h.sets + 1] = k end,
        osd_message = function(text, duration) h.osds[#h.osds + 1] = {text = text, duration = duration} end,
        add_key_binding = function(key, name, fn) h.keys[#h.keys + 1] = key; h.bindings[name] = fn end}
    dofile(SCRIPT)
    return h
end

test('binding registered keyless under name "toggle"', function()
    local h = load(DEFAULT)
    eq('function', type(h.bindings['toggle']))
    eq(nil, h.keys[1]) -- keyless: input.conf owns b and its twin
end)

test('on draws the box, off restores the default border style', function()
    local h = load(DEFAULT)
    h.bindings['toggle']()
    eq('background-box', h.props['sub-border-style'])
    eq(DEFAULT, h.props['sub-back-color'])
    eq('Subtitle backdrop: on', h.osds[1].text)
    h.bindings['toggle']()
    eq('outline-and-shadow', h.props['sub-border-style'])
    eq(DEFAULT, h.props['sub-back-color'])
    eq('Subtitle backdrop: off', h.osds[2].text)
end)

test('only the border style changes: the colour is never written', function()
    local h = load('#FF123456')
    h.bindings['toggle']()
    h.bindings['toggle']()
    for _, key in ipairs(h.sets) do eq('sub-border-style', key) end
    eq('#FF123456', h.props['sub-back-color'])
end)

test('a transparent colour gets a visible box, and is restored on off', function()
    local h = load(TRANSPARENT)
    h.bindings['toggle']()
    eq('background-box', h.props['sub-border-style'])
    eq(DEFAULT, h.props['sub-back-color'])
    h.bindings['toggle']()
    eq('outline-and-shadow', h.props['sub-border-style'])
    eq(TRANSPARENT, h.props['sub-back-color'])
end)

print('sub_backdrop: '..total..' tests passed')
