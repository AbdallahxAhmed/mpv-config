local total=0
local function eq(a,b) assert(a==b,tostring(a)..' ~= '..tostring(b)) end
local function test(name,fn) fn(); total=total+1; print('ok sub_backdrop: '..name) end

-- Regression targets:
--  1) pressing b when the backdrop is on stores the current color, goes
--     transparent and shows "Subtitle backdrop: off"
--  2) pressing b again restores the STORED color (not the template default)
--     and shows "Subtitle backdrop: on"
--  3) a transparent session start still enables with the template default
--  4) the binding is registered KEYLESS: keys live in input.conf only

local here = debug.getinfo(1,'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or './') .. '/'
-- here already ends with a separator when match succeeded; normalize both cases
if not here:match('[/\\]$') and here ~= './' then here = here .. '/' end

local DEFAULT = '#B3080808'
local OFF = '#00000000'
local SCRIPT = here .. '../../scripts/sub_backdrop.lua'

local function harness(default_color)
    _G.mp = nil
    local h={props={}, bindings={}, keys={}, osds={}}
    h.props['sub-back-color'] = default_color
    _G.mp={log=function() end,
        get_property=function(k,d) local v=h.props[k]; if v==nil then return d end; return v end,
        set_property=function(k,v) h.props[k]=v end,
        osd_message=function(text,duration) h.osds[#h.osds+1]={text=text,duration=duration} end,
        add_key_binding=function(key,name,fn) h.keys[#h.keys+1]=key; h.bindings[name]=fn end}
    return h
end

local function load(harness_color)
    local h = harness(harness_color)
    dofile(SCRIPT)
    return h
end

test('binding registered keyless under name "toggle"', function()
    local h = load(DEFAULT)
    eq('function', type(h.bindings['toggle']))
    eq(nil, h.keys[1]) -- keyless: input.conf owns b and ب
end)

test('off stores the current color, shows "off"; on restores it', function()
    local h = load(DEFAULT)
    local fn = h.bindings['toggle']

    fn()
    eq(OFF, h.props['sub-back-color'])
    eq('Subtitle backdrop: off', h.osds[1].text)

    fn()
    eq(DEFAULT, h.props['sub-back-color'])
    eq('Subtitle backdrop: on', h.osds[2].text)
end)

test('restores the preset color actually in use, not the template default', function()
    local h = load('#FF123456')
    local fn = h.bindings['toggle']

    fn()
    eq(OFF, h.props['sub-back-color'])
    fn()
    eq('#FF123456', h.props['sub-back-color'])
end)

test('transparent session start enables with the template default', function()
    local h = load(OFF)
    h.bindings['toggle']()
    eq(DEFAULT, h.props['sub-back-color'])
    eq('Subtitle backdrop: on', h.osds[1].text)
end)

print('sub_backdrop: '..total..' tests passed')
