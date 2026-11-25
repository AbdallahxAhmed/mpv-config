-- tests/lua/test_more_menu.lua: tests for More menu script (spec 006 T004-T006)
local total = 0
local function eq(a, b, msg)
    if a ~= b then
        error(debug.traceback('ASSERTION FAILED: ' .. tostring(a) .. ' ~= ' .. tostring(b) .. (msg and (' (' .. msg .. ')') or ''), 2))
    end
end
local function test(name, fn)
    fn()
    total = total + 1
    io.stdout:write('ok more_menu: ' .. name .. '\n')
    io.stdout:flush()
end

local here = debug.getinfo(1, 'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or './') .. '/'
if not here:match('[/\\]$') and here ~= './' then here = here .. '/' end

local SCRIPT = here .. '../../scripts/more_menu.lua'

local function sandbox_conf(content)
    local path = os.tmpname()
    local f = io.open(path, 'w')
    if f then
        f:write(content)
        f:close()
    end
    return path
end

local function create_harness(props, uosc_conf_path)
    local h = {
        props = props or {},
        commands = {},
        messages = {},
        observers = {},
        uosc_conf_path = uosc_conf_path,
    }
    _G.mp = {
        log = function() end,
        msg = {
            warn = function() end,
            info = function() end,
            debug = function() end,
            error = function() end,
        },
        get_property_native = function(k, d)
            local v = h.props[k]
            if v == nil then return d end
            return v
        end,
        set_property_native = function(k, v)
            h.props[k] = v
        end,
        get_property = function(k, d)
            local v = h.props[k]
            if v == nil then return d end
            return v
        end,
        get_property_bool = function(k, d)
            local v = h.props[k]
            if v == nil then return d end
            if type(v) == 'boolean' then return v end
            return v == 'yes' or v == 'true'
        end,
        commandv = function(...)
            h.commands[#h.commands + 1] = { ... }
        end,
        command_native = function(cmd)
            if type(cmd) == 'table' and cmd[1] == 'expand-path' then
                if cmd[2] == '~~/script-opts/uosc.conf' then
                    return h.uosc_conf_path or '~~/script-opts/uosc.conf'
                end
            end
            return nil
        end,
        register_script_message = function(name, fn)
            h.messages[name] = fn
        end,
        observe_property = function(name, _, fn)
            h.observers[name] = fn
        end,
        find_config_file = function(path)
            if path == 'script-opts/uosc.conf' then
                return h.uosc_conf_path
            end
            return nil
        end,
        get_script_name = function() return 'more_menu' end,
    }
    return h
end

test('open script message opens More menu with correct type, title and rows', function()
    local h = create_harness({
        ['demuxer-via-network'] = true,
        ['edition-list'] = {{id = 0}, {id = 1}},
        ['loop-playlist'] = 'inf',
        ['loop-file'] = 'no',
        ['user-data/player_toolbar/stable-volume'] = true,
    })
    dofile(SCRIPT)

    assert(h.messages['open'] ~= nil, 'open message must be registered')
    h.messages['open']()

    eq(#h.commands, 1, 'expected 1 command on open')
    local cmd = h.commands[1]
    eq(cmd[1], 'script-message-to')
    eq(cmd[2], 'uosc')
    eq(cmd[3], 'open-menu')

    local utils = require 'mp.utils'
    local menu = utils.parse_json(cmd[4])
    eq(menu.type, 'more_menu')
    eq(menu.title, 'More')
    eq(#menu.items, 9, 'should have 9 rows when stream and multi-edition')

    -- Exact order from spec:
    -- 1. Paste link (hint Ctrl+V)
    eq(menu.items[1].title, 'Paste link')
    eq(menu.items[1].hint, 'Ctrl+V')
    eq(menu.items[1].value, 'script-binding smart_paste/paste-to-open')
    eq(menu.items[1].keep_open, nil)

    -- 2. Download video
    eq(menu.items[2].title, 'Download video')
    eq(menu.items[2].value, 'script-message-to player_toolbar download-video')
    eq(menu.items[2].keep_open, nil)

    -- 3. Stable volume
    eq(menu.items[3].title, 'Stable volume')
    eq(menu.items[3].value, 'script-message-to player_toolbar toggle-stable-volume')
    eq(menu.items[3].keep_open, true)
    eq(menu.items[3].active, true)

    -- 4. Shuffle
    eq(menu.items[4].title, 'Shuffle')
    eq(menu.items[4].value, 'script-message-to more_menu toggle-shuffle')
    eq(menu.items[4].keep_open, true)
    eq(menu.items[4].active, nil)

    -- 5. Loop playlist
    eq(menu.items[5].title, 'Loop playlist')
    eq(menu.items[5].value, 'cycle-values loop-playlist inf no')
    eq(menu.items[5].keep_open, true)
    eq(menu.items[5].active, true)

    -- 6. Loop file
    eq(menu.items[6].title, 'Loop file')
    eq(menu.items[6].value, 'cycle-values loop-file inf no')
    eq(menu.items[6].keep_open, true)
    eq(menu.items[6].active, nil)

    -- 7. Editions
    eq(menu.items[7].title, 'Editions')
    eq(menu.items[7].value, 'script-binding uosc/editions')
    eq(menu.items[7].keep_open, nil)

    -- 8. Full uosc menu
    eq(menu.items[8].title, 'Full uosc menu')
    eq(menu.items[8].value, 'script-binding uosc/menu-blurred')
    eq(menu.items[8].keep_open, nil)

    -- 9. All shortcuts (hint F9)
    eq(menu.items[9].title, 'All shortcuts')
    eq(menu.items[9].hint, 'F9')
    eq(menu.items[9].value, 'script-message-to help_overlay help')
    eq(menu.items[9].keep_open, nil)
end)

test('conditional rows: Download video only on stream, Editions only with >1 edition', function()
    -- Local video with single edition
    local h = create_harness({
        ['demuxer-via-network'] = false,
        ['edition-list'] = {{id = 0}},
    })
    dofile(SCRIPT)

    h.messages['open']()
    local utils = require 'mp.utils'
    local menu = utils.parse_json(h.commands[1][4])
    eq(#menu.items, 7, 'expected 7 rows without Download video and Editions')

    for _, it in ipairs(menu.items) do
        assert(it.title ~= 'Download video', 'Download video should not be present for local video')
        assert(it.title ~= 'Editions', 'Editions should not be present with <= 1 edition')
    end
end)

test('open while more_menu is open closes it', function()
    local h = create_harness({
        ['user-data/uosc/menu/type'] = 'more_menu',
    })
    dofile(SCRIPT)

    h.messages['open']()
    eq(#h.commands, 1)
    eq(h.commands[1][1], 'script-message-to')
    eq(h.commands[1][2], 'uosc')
    eq(h.commands[1][3], 'close-menu')
    eq(h.commands[1][4], 'more_menu')
end)

test('property change sends update-menu', function()
    local h = create_harness({
        ['loop-playlist'] = 'no',
        ['loop-file'] = 'no',
        ['user-data/player_toolbar/stable-volume'] = false,
    })
    dofile(SCRIPT)

    assert(h.observers['loop-playlist'] ~= nil, 'observer for loop-playlist required')
    assert(h.observers['loop-file'] ~= nil, 'observer for loop-file required')
    assert(h.observers['user-data/player_toolbar/stable-volume'] ~= nil, 'observer for stable-volume required')

    local cmds_before = #h.commands
    h.props['loop-playlist'] = 'inf'
    h.observers['loop-playlist']()

    eq(#h.commands, cmds_before + 1)
    local update_cmd = h.commands[#h.commands]
    eq(update_cmd[1], 'script-message-to')
    eq(update_cmd[2], 'uosc')
    eq(update_cmd[3], 'update-menu')

    local utils = require 'mp.utils'
    local menu = utils.parse_json(update_cmd[4])
    eq(menu.type, 'more_menu')
    for _, it in ipairs(menu.items) do
        if it.title == 'Loop playlist' then
            eq(it.active, true)
        end
    end
end)

test('shuffle flag initializes from uosc.conf and flips on toggle-shuffle', function()
    -- 1. uosc.conf with shuffle=yes
    local conf_yes = sandbox_conf("# uosc options\nshuffle=no\nshuffle=yes\n")
    local h1 = create_harness({}, conf_yes)
    dofile(SCRIPT)

    h1.messages['open']()
    local utils = require 'mp.utils'
    local menu1 = utils.parse_json(h1.commands[#h1.commands][4])
    local shuf1
    for _, it in ipairs(menu1.items) do
        if it.title == 'Shuffle' then shuf1 = it break end
    end
    assert(shuf1 ~= nil)
    eq(shuf1.active, true)

    -- Toggle shuffle: runs uosc/shuffle, flips flag, sends update-menu
    local cmds_before = #h1.commands
    h1.messages['toggle-shuffle']()
    eq(#h1.commands, cmds_before + 2)
    eq(h1.commands[cmds_before + 1][1], 'script-binding')
    eq(h1.commands[cmds_before + 1][2], 'uosc/shuffle')
    eq(h1.commands[cmds_before + 2][1], 'script-message-to')
    eq(h1.commands[cmds_before + 2][2], 'uosc')
    eq(h1.commands[cmds_before + 2][3], 'update-menu')

    local menu_toggled = utils.parse_json(h1.commands[cmds_before + 2][4])
    for _, it in ipairs(menu_toggled.items) do
        if it.title == 'Shuffle' then eq(it.active, nil) end
    end
    pcall(os.remove, conf_yes)

    -- 2. uosc.conf with shuffle=no
    local conf_no = sandbox_conf("shuffle=no\n")
    local h2 = create_harness({}, conf_no)
    dofile(SCRIPT)

    h2.messages['open']()
    local menu2 = utils.parse_json(h2.commands[#h2.commands][4])
    for _, it in ipairs(menu2.items) do
        if it.title == 'Shuffle' then eq(it.active, nil) end
    end
    pcall(os.remove, conf_no)
end)

print(string.format('More menu tests passed: %d', total))
