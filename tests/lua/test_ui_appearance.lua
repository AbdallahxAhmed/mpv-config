-- tests/lua/test_ui_appearance.lua: tests for spec 006 P1 (looks, load, More menu, contrast)
local total = 0
local function eq(a, b, msg)
    if a ~= b then
        error(debug.traceback('ASSERTION FAILED: ' .. tostring(a) .. ' ~= ' .. tostring(b) .. (msg and (' (' .. msg .. ')') or ''), 2))
    end
end
local function test(name, fn)
    fn()
    total = total + 1
    io.stdout:write('ok ui_appearance: ' .. name .. '\n')
    io.stdout:flush()
end

local here = debug.getinfo(1, 'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or './') .. '/'
if not here:match('[/\\]$') and here ~= './' then here = here .. '/' end

local LOOKS_MODULE = here .. '../../scripts/modules/looks.lua'
local SCRIPT = here .. '../../scripts/ui_appearance.lua'
local CONF_SHIPPED = here .. '../../config/script-opts/ui_appearance.conf'
local INPUT_CONF_TEMPLATE = here .. '../../config/input.conf.template'
local UOSC_OPTIONS_JSON = here .. '../fixtures/uosc-5.13.0/uosc-options.json'
local SCRIPT_PLAYER_TOOLBAR = here .. '../../scripts/player-toolbar.lua'
local SCRIPT_PROFILE_PICKER = here .. '../../scripts/profile_picker.lua'
local SCRIPT_HELP_OVERLAY = here .. '../../scripts/help_overlay.lua'

local ok_looks, looks = pcall(dofile, LOOKS_MODULE)
if not ok_looks or type(looks) ~= 'table' then
    error('Failed to load looks module: ' .. tostring(looks))
end

-- ── T001: looks module tests ──────────────────────────────────────────

test('looks.CHOICES enumerates exactly 90 looks with valid owned keys and orders', function()
    local count = 0
    for _, style in ipairs(looks.CHOICES.style) do
        for _, bg in ipairs(looks.CHOICES.background) do
            for _, acc in ipairs(looks.CHOICES.accent) do
                for _, sz in ipairs(looks.CHOICES.size) do
                    count = count + 1
                    local look = {style = style, background = bg, accent = acc, size = sz}
                    local opts = looks.uosc_options(look)

                    -- Only OWNED_KEYS are produced
                    local k_count = 0
                    for k, _ in pairs(opts) do
                        k_count = k_count + 1
                        local base_k = k:match('^uosc%-(.*)$')
                        assert(base_k ~= nil, 'key without uosc- prefix: ' .. tostring(k))
                        local found = false
                        for _, owned in ipairs(looks.OWNED_KEYS) do
                            if owned == base_k then found = true; break end
                        end
                        assert(found, 'unknown owned key: ' .. base_k)
                    end
                    eq(k_count, #looks.OWNED_KEYS, 'owned key count mismatch')

                    -- Color sub-keys order
                    local color_str = opts['uosc-color']
                    local color_keys = {}
                    for pair in color_str:gmatch('[^,]+') do
                        local ck = pair:match('^([^=]+)=')
                        color_keys[#color_keys + 1] = ck
                    end
                    eq(#color_keys, #looks.OWNED_COLOR_KEYS, 'color subkey count')
                    for idx, expected_ck in ipairs(looks.OWNED_COLOR_KEYS) do
                        eq(color_keys[idx], expected_ck, 'color subkey order')
                    end

                    -- Opacity sub-keys order
                    local opac_str = opts['uosc-opacity']
                    local opac_keys = {}
                    for pair in opac_str:gmatch('[^,]+') do
                        local ok = pair:match('^([^=]+)=')
                        opac_keys[#opac_keys + 1] = ok
                    end
                    eq(#opac_keys, #looks.OWNED_OPACITY_KEYS, 'opacity subkey count')
                    for idx, expected_ok in ipairs(looks.OWNED_OPACITY_KEYS) do
                        eq(opac_keys[idx], expected_ok, 'opacity subkey order')
                    end
                end
            end
        end
    end
    eq(count, 90, 'total looks count')
end)

test('default look options match literal values from data-model.md', function()
    local opts = looks.uosc_options(looks.DEFAULTS)
    eq(opts['uosc-controls'], 'prev,cycle:pause_circle:pause:no=pause_circle/yes=play_circle?Play/pause,next,space,<video,audio>speed,command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles,button:audio-tracks,<has_many_video>video,<has_many_edition>editions,<stream>button:stream-quality,<stream>button:download-video,items,command:menu:script-message-to ui_appearance open-more?More,fullscreen')
    eq(opts['uosc-color'], 'foreground=f2b544,foreground_text=000000,background=0e0f12,background_text=f2f2f3,window_border=000000,curtain=06080d,success=34d399,error=f87171,match=38bdf8,heatmap=00adee')
    eq(opts['uosc-opacity'], 'timeline=0.95,position=1,chapters=0.8,slider=0.95,slider_gauge=1,controls=0,speed=0.7,menu=0.95,submenu=0.5,border=1,title=1,tooltip=1,thumbnail=1,curtain=0.85,idle_indicator=0.85,audio_indicator=0.6,buffering_indicator=0.4,playlist_position=0.8,heatmap=0.4')
    eq(opts['uosc-controls_size'], '44')
    eq(opts['uosc-controls_spacing'], '4')
    eq(opts['uosc-controls_margin'], '8')
    eq(opts['uosc-controls_persistency'], 'idle')
    eq(opts['uosc-timeline_size'], '40')
    eq(opts['uosc-progress'], 'always')
    eq(opts['uosc-progress_size'], '3')
    eq(opts['uosc-menu_item_height'], '40')
end)

test('focus and bar controls and persistency behave as specified', function()
    local focus_opts = looks.uosc_options({style = 'focus', background = 'dark', accent = 'amber', size = 'comfortable'})
    local calm_opts = looks.uosc_options({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'})
    local bar_opts = looks.uosc_options({style = 'bar', background = 'dark', accent = 'amber', size = 'comfortable'})

    eq(focus_opts['uosc-controls'], 'space,prev,cycle:pause_circle:pause:no=pause_circle/yes=play_circle?Play/pause,next,space,items,command:menu:script-message-to ui_appearance open-more?More,fullscreen')
    eq(bar_opts['uosc-controls'], calm_opts['uosc-controls'])
    eq(bar_opts['uosc-controls_persistency'], 'idle,windowed')
    eq(calm_opts['uosc-controls_persistency'], 'idle')

    -- bar differs from calm only in opacity.controls=0.93 and controls_persistency=idle,windowed
    for k, v in pairs(calm_opts) do
        if k == 'uosc-controls_persistency' then
            eq(bar_opts[k], 'idle,windowed')
        elseif k == 'uosc-opacity' then
            local calm_opac = v
            local bar_opac = bar_opts[k]
            eq(calm_opac:gsub('controls=0', 'controls=0.93'), bar_opac)
        else
            eq(bar_opts[k], v, 'key mismatch between bar and calm: ' .. k)
        end
    end
end)

test('merge_script_opts preserves foreign entries and updates owned keys', function()
    local current = {
        ['display_fps_guard-detected_fps'] = '144',
        ['uosc-controls_size'] = '999',
        ['custom_other_key'] = 'hello',
    }
    local merged = looks.merge_script_opts(current, looks.DEFAULTS)
    eq(merged['display_fps_guard-detected_fps'], '144')
    eq(merged['custom_other_key'], 'hello')
    eq(merged['uosc-controls_size'], '44')
    for _, k in ipairs(looks.OWNED_KEYS) do
        assert(merged['uosc-' .. k] ~= nil, 'missing owned key: ' .. k)
    end
end)

test('normalize handles empty, invalid, and partial values in DEFAULTS order', function()
    local look1, fallbacks1 = looks.normalize({})
    eq(look1.style, 'calm')
    eq(look1.background, 'dark')
    eq(look1.accent, 'amber')
    eq(look1.size, 'comfortable')
    eq(#fallbacks1, 4)
    eq(fallbacks1[1], 'style')
    eq(fallbacks1[2], 'background')
    eq(fallbacks1[3], 'accent')
    eq(fallbacks1[4], 'size')

    local look2, fallbacks2 = looks.normalize({
        style = 'huge',
        background = 'dark',
        accent = 'teal',
        size = '',
    })
    eq(look2.style, 'calm')
    eq(look2.background, 'dark')
    eq(look2.accent, 'teal')
    eq(look2.size, 'comfortable')
    eq(#fallbacks2, 2)
    eq(fallbacks2[1], 'style')
    eq(fallbacks2[2], 'size')
end)

test('serialize(DEFAULTS) is byte-equal to shipped ui_appearance.conf', function()
    local serialized = looks.serialize(looks.DEFAULTS)
    local f = io.open(CONF_SHIPPED, 'r')
    assert(f ~= nil, 'could not open ' .. CONF_SHIPPED)
    local content = f:read('*a')
    f:close()
    eq(serialized, content)
end)

-- ── T002: script-level tests for ui_appearance.lua ────────────────────

local function sandbox_conf(initial_content)
    local tmpdir = os.getenv('TEMP') or os.getenv('TMPDIR') or os.getenv('TMP') or '/tmp'
    local sep = (tmpdir:sub(-1) == '/' or tmpdir:sub(-1) == '\\') and '' or '/'
    local path = tmpdir .. sep .. 'test_ui_appearance_' .. tostring(os.time()) .. '_' .. tostring(math.random(100000, 999999)) .. '.conf'
    if initial_content then
        local f = assert(io.open(path, 'w'))
        f:write(initial_content)
        f:close()
    end
    return path
end

local function create_script_harness(raw_opts, script_opts, conf_path, uosc_conf_path)
    local h = {
        props = {
            ['script-opts'] = script_opts or {},
        },
        warnings = {},
        commands = {},
        messages = {},
        observers = {},
        osd_messages = {},
        set_property_native_calls = 0,
        conf_path = conf_path,
        conf_exists = conf_path and true or false,
        uosc_conf_path = uosc_conf_path,
        uosc_conf_exists = uosc_conf_path and true or false,
    }
    if conf_path then
        local f = io.open(conf_path, 'r')
        if f then
            f:close()
            h.conf_exists = true
        else
            h.conf_exists = false
        end
    end
    if uosc_conf_path then
        local f = io.open(uosc_conf_path, 'r')
        if f then
            f:close()
            h.uosc_conf_exists = true
        else
            h.uosc_conf_exists = false
        end
    end
    _G.mp = {
        log = function() end,
        msg = {
            warn = function(msg) h.warnings[#h.warnings + 1] = msg end,
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
            if k == 'script-opts' then
                h.set_property_native_calls = h.set_property_native_calls + 1
            end
            h.props[k] = v
        end,
        get_property = function(k, d)
            if k == 'config-dir' and h.conf_path then
                return (h.conf_path:match('^(.*[/\\])[^/\\]+$') or './')
            end
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
                return h.conf_path or '~~/script-opts/ui_appearance.conf'
            end
            return nil
        end,
        register_script_message = function(name, fn)
            h.messages[name] = fn
        end,
        observe_property = function(name, _, fn)
            h.observers[name] = fn
        end,
        osd_message = function(text, timeout)
            h.osd_messages[#h.osd_messages + 1] = {text = text, timeout = timeout}
        end,
        find_config_file = function(path)
            if path == 'scripts/modules/looks.lua' then
                return LOOKS_MODULE
            end
            if path == 'script-opts/ui_appearance.conf' then
                if h.conf_exists and h.conf_path then
                    return h.conf_path
                end
                return nil
            end
            if path == 'script-opts/uosc.conf' then
                if h.uosc_conf_exists and h.uosc_conf_path then
                    return h.uosc_conf_path
                end
                return nil
            end
            return nil
        end,
    }
    package.loaded['mp.options'] = nil
    package.preload['mp.options'] = function()
        return {
            read_options = function(target, name)
                if raw_opts then
                    for k, v in pairs(raw_opts) do
                        target[k] = v
                    end
                end
            end,
        }
    end
    package.loaded['mp.msg'] = nil
    package.preload['mp.msg'] = function() return _G.mp.msg end
    return h
end

test('load makes exactly one set_property_native call for script-opts', function()
    local h = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'})
    dofile(SCRIPT)
    eq(h.set_property_native_calls, 1)
    eq(h.props['script-opts']['uosc-controls_size'], '44')
end)

test('load with missing file logs exactly one warning naming all four fields', function()
    local h = create_script_harness({})
    dofile(SCRIPT)
    eq(#h.warnings, 1)
    assert(h.warnings[1]:find('style, background, accent, size') ~= nil, 'warning should name all four fields: ' .. h.warnings[1])
end)

test('load with style=huge logs one warning naming style', function()
    local h = create_script_harness({style = 'huge', background = 'dark', accent = 'amber', size = 'comfortable'})
    dofile(SCRIPT)
    eq(#h.warnings, 1)
    assert(h.warnings[1]:find('style') ~= nil, 'warning should name style: ' .. h.warnings[1])
end)

test('load with no uosc present raises no error', function()
    local h = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'})
    local ok, err = pcall(dofile, SCRIPT)
    eq(ok, true, 'script failed to load: ' .. tostring(err))
end)

test('open-more sends one script-message-to uosc open-menu with full More menu', function()
    local h = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'})
    dofile(SCRIPT)
    assert(h.messages['open-more'] ~= nil, 'open-more not registered')
    h.messages['open-more']()
    eq(#h.commands, 1)
    local cmd = h.commands[1]
    eq(cmd[1], 'script-message-to')
    eq(cmd[2], 'uosc')
    eq(cmd[3], 'open-menu')

    local utils = require 'mp.utils'
    local menu = utils.parse_json(cmd[4])
    eq(menu.type, 'ui_appearance_more')
    eq(menu.title, 'More')
    eq(#menu.items, 8)

    eq(menu.items[1].title, 'Appearance')
    eq(menu.items[2].title, 'Subtitles')
    eq(menu.items[2].value, 'script-binding ytdl_sub_menu/open')
    eq(menu.items[3].title, 'Audio')
    eq(menu.items[3].value, 'script-message-to player_toolbar open-audio-menu')
    eq(menu.items[4].title, 'Playback')
    eq(menu.items[5].title, 'Picture & sound')
    eq(menu.items[6].title, 'Open')
    eq(menu.items[7].title, 'Full uosc menu')
    eq(menu.items[7].value, 'script-binding uosc/menu-blurred')
    eq(menu.items[8].title, 'All shortcuts')
    eq(menu.items[8].hint, 'F9')
    eq(menu.items[8].value, 'script-message-to help_overlay help')

    eq(#menu.items[6].items, 2)
    eq(menu.items[6].items[1].title, 'Paste link')
    eq(menu.items[6].items[1].hint, 'Ctrl+V')
    eq(menu.items[6].items[1].value, 'script-binding smart_paste/paste-to-open')
    eq(menu.items[6].items[2].title, 'Open file')
    eq(menu.items[6].items[2].value, 'script-binding uosc/open-file')
end)

-- ── T003: contrast test from research R6 ──────────────────────────────

test('contrast model satisfies WCAG thresholds across all 15 background x accent pairs', function()
    local title = looks.TEXT_COLOR
    local backgrounds = looks.BACKGROUND_COLORS
    local accents = looks.ACCENT_COLORS

    local function assert_contrast(fg, bg, threshold, label, bg_name, acc_name)
        local ratio = looks.contrast(fg, bg)
        if ratio < threshold then
            error(string.format('Contrast failure for %s x %s (%s): ratio %.2f < threshold %.2f (fg=%s, bg=%s)',
                bg_name, acc_name, label, ratio, threshold, fg, bg))
        end
    end

    local count = 0
    for bg_name, bg_hex in pairs(backgrounds) do
        for acc_name, acc_hex in pairs(accents) do
            count = count + 1
            for _, under in ipairs({'000000', 'ffffff'}) do
                local surface = looks.blend(bg_hex, 0.95, under)
                local bar_box = looks.blend(bg_hex, looks.BAR_BOX_OPACITY, under)

                -- 1. Title on surface >= 4.5
                assert_contrast(title, surface, 4.5, 'Title on surface (under=' .. under .. ')', bg_name, acc_name)

                -- 2. Hint or muted on surface >= 3.0 (title at 0.5 over surface)
                local hint_surf = looks.blend(title, 0.5, surface)
                assert_contrast(hint_surf, surface, 3.0, 'Hint on surface (under=' .. under .. ')', bg_name, acc_name)

                -- 3. Title on hover row >= 4.5 (accent at 0.15 over surface)
                local hover = looks.blend(acc_hex, 0.15, surface)
                assert_contrast(title, hover, 4.5, 'Title on hover row (under=' .. under .. ')', bg_name, acc_name)

                -- 4. Hint on hover row >= 3.0
                local hint_hover = looks.blend(title, 0.5, hover)
                assert_contrast(hint_hover, hover, 3.0, 'Hint on hover row (under=' .. under .. ')', bg_name, acc_name)

                -- 5. 000000 on active row >= 4.5 (accent at 0.8 over surface)
                local active_row = looks.blend(acc_hex, 0.8, surface)
                assert_contrast('000000', active_row, 4.5, '000000 on active row (under=' .. under .. ')', bg_name, acc_name)

                -- 6. Accent icon on surface >= 4.5
                assert_contrast(acc_hex, surface, 4.5, 'Accent icon on surface (under=' .. under .. ')', bg_name, acc_name)

                -- 7. Accent icon on bar box >= 4.5 (Background at 0.93 over under)
                assert_contrast(acc_hex, bar_box, 4.5, 'Accent icon on bar box (under=' .. under .. ')', bg_name, acc_name)

                -- Exempt: hint on active row is NOT checked
            end

            -- 8. Background-coloured icon on accent >= 4.5
            assert_contrast(bg_hex, acc_hex, 4.5, 'Background icon on accent', bg_name, acc_name)
        end
    end
    eq(count, 15, 'total background x accent pairs checked')
end)

test('more_menu puts Appearance first with Style, Background, Accent, Size marking current look', function()
    local look = {style = 'bar', background = 'black', accent = 'teal', size = 'compact'}
    local menu = looks.more_menu(look)
    eq(menu.type, 'ui_appearance_more')
    eq(menu.title, 'More')
    eq(#menu.items, 8)

    local app = menu.items[1]
    eq(app.title, 'Appearance')
    assert(type(app.items) == 'table', 'Appearance items must be table')
    eq(#app.items, 4)

    local expected_fields = {
        {field = 'style', title = 'Style', choices = looks.CHOICES.style, current = 'bar'},
        {field = 'background', title = 'Background', choices = looks.CHOICES.background, current = 'black'},
        {field = 'accent', title = 'Accent', choices = looks.CHOICES.accent, current = 'teal'},
        {field = 'size', title = 'Size', choices = looks.CHOICES.size, current = 'compact'},
    }

    for f_idx, exp in ipairs(expected_fields) do
        local sub = app.items[f_idx]
        eq(sub.title, exp.title)
        eq(#sub.items, #exp.choices)
        for c_idx, val in ipairs(exp.choices) do
            local item = sub.items[c_idx]
            eq(item.title, val)
            eq(item.value, 'script-message-to ui_appearance set ' .. exp.field .. ' ' .. val)
            eq(item.keep_open, true)
            if val == exp.current then
                eq(item.active, true)
                eq(item.hint, nil, 'active row must not carry hint')
            else
                eq(item.active, nil)
            end
        end
    end

    -- Following rows in More menu
    eq(menu.items[2].title, 'Subtitles')
    eq(menu.items[3].title, 'Audio')
    eq(menu.items[4].title, 'Playback')
    eq(menu.items[5].title, 'Picture & sound')
    eq(menu.items[6].title, 'Open')
    eq(menu.items[7].title, 'Full uosc menu')
    eq(menu.items[8].title, 'All shortcuts')
    eq(menu.items[8].hint, 'F9')

    -- Paste link moved into Open
    eq(menu.items[6].items[1].title, 'Paste link')
    eq(menu.items[6].items[1].hint, 'Ctrl+V')

    -- Stable volume moved into Picture & sound
    eq(menu.items[5].items[2].title, 'Stable volume')
end)

-- ── T019 & T020: pick tests and windows save tests ───────────────────

test('set writes file before its one script-opts write and sends update-menu', function()
    local conf = sandbox_conf(looks.serialize(looks.DEFAULTS))
    local h = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'}, {}, conf)

    local events = {}
    local orig_io_open = io.open
    _G.io.open = function(path, mode)
        if path == conf and mode == 'w' then
            events[#events + 1] = 'file_open'
            local f = orig_io_open(path, mode)
            return {
                write = function(self, text)
                    events[#events + 1] = 'file_write'
                    return f:write(text)
                end,
                close = function(self)
                    events[#events + 1] = 'file_close'
                    return f:close()
                end,
            }
        end
        return orig_io_open(path, mode)
    end

    local orig_set_prop = mp.set_property_native
    mp.set_property_native = function(k, v)
        if k == 'script-opts' then
            events[#events + 1] = 'script_opts'
        end
        return orig_set_prop(k, v)
    end

    dofile(SCRIPT)
    events = {}
    local set_calls_before = h.set_property_native_calls
    local cmds_before = #h.commands

    assert(h.messages['set'] ~= nil, 'set message not registered')
    h.messages['set']('style', 'bar')

    _G.io.open = orig_io_open
    mp.set_property_native = orig_set_prop

    local write_idx, opts_idx
    for i, ev in ipairs(events) do
        if ev == 'file_write' and not write_idx then write_idx = i end
        if ev == 'script_opts' and not opts_idx then opts_idx = i end
    end
    assert(write_idx ~= nil, 'file write did not occur')
    assert(opts_idx ~= nil, 'script-opts write did not occur')
    assert(write_idx < opts_idx, 'file write must happen before script-opts write')

    local expected_look = {style = 'bar', background = 'dark', accent = 'amber', size = 'comfortable'}
    local f = io.open(conf, 'r')
    local content = f:read('*a')
    f:close()
    eq(content, looks.serialize(expected_look))

    eq(h.set_property_native_calls, set_calls_before + 1)
    eq(h.props['script-opts']['uosc-controls_persistency'], 'idle,windowed')

    eq(#h.commands, cmds_before + 1)
    local cmd = h.commands[#h.commands]
    eq(cmd[1], 'script-message-to')
    eq(cmd[2], 'uosc')
    eq(cmd[3], 'update-menu')
    local utils = require 'mp.utils'
    local menu = utils.parse_json(cmd[4])
    eq(menu.type, 'ui_appearance_more')
    eq(menu.items[1].items[1].items[2].active, true)

    pcall(os.remove, conf)
end)

test('three quick picks give three writes and the last one wins', function()
    local conf = sandbox_conf(looks.serialize(looks.DEFAULTS))
    local h = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'}, {}, conf)
    dofile(SCRIPT)
    local set_calls_before = h.set_property_native_calls

    assert(h.messages['set'] ~= nil, 'set message not registered')
    h.messages['set']('style', 'bar')
    h.messages['set']('accent', 'teal')
    h.messages['set']('style', 'focus')

    eq(h.set_property_native_calls, set_calls_before + 3)

    local expected_look = {style = 'focus', background = 'dark', accent = 'teal', size = 'comfortable'}
    local f = io.open(conf, 'r')
    local content = f:read('*a')
    f:close()
    eq(content, looks.serialize(expected_look))

    local focus_opts = looks.uosc_options(expected_look)
    for k, v in pairs(focus_opts) do
        eq(h.props['script-opts'][k], v)
    end

    pcall(os.remove, conf)
end)

test('failed save shows osd message and still applies look', function()
    local conf = sandbox_conf(looks.serialize(looks.DEFAULTS))
    local h = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'}, {}, conf)
    dofile(SCRIPT)

    local orig_io_open = io.open
    _G.io.open = function(...) return nil, 'Permission denied' end

    assert(h.messages['set'] ~= nil, 'set message not registered')
    h.messages['set']('style', 'bar')

    _G.io.open = orig_io_open

    eq(#h.osd_messages, 1)
    eq(h.osd_messages[1].text, 'Appearance not saved: Permission denied')
    eq(h.osd_messages[1].timeout, 3)

    eq(h.props['script-opts']['uosc-controls_persistency'], 'idle,windowed')

    local cmd = h.commands[#h.commands]
    eq(cmd[3], 'update-menu')

    pcall(os.remove, conf)
end)

test('invalid field or value logs warning and does not write or apply', function()
    local conf = sandbox_conf(looks.serialize(looks.DEFAULTS))
    local h = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'}, {}, conf)
    dofile(SCRIPT)

    local writes_before = h.set_property_native_calls
    local cmds_before = #h.commands
    local warns_before = #h.warnings

    assert(h.messages['set'] ~= nil, 'set message not registered')
    h.messages['set']('style', 'huge')
    eq(#h.warnings, warns_before + 1)
    eq(h.set_property_native_calls, writes_before)
    eq(#h.commands, cmds_before)

    h.messages['set']('colour', 'amber')
    eq(#h.warnings, warns_before + 2)
    eq(h.set_property_native_calls, writes_before)
    eq(#h.commands, cmds_before)

    local f = io.open(conf, 'r')
    local content = f:read('*a')
    f:close()
    eq(content, looks.serialize(looks.DEFAULTS))

    pcall(os.remove, conf)
end)

test('windows save writes in place without os.rename or os.remove', function()
    local conf = sandbox_conf(looks.serialize(looks.DEFAULTS))
    local h = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'}, {}, conf)
    dofile(SCRIPT)

    local rename_calls = 0
    local remove_calls = 0
    local orig_rename = os.rename
    local orig_remove = os.remove
    _G.os.rename = function() rename_calls = rename_calls + 1; error('Windows rename failure') end
    _G.os.remove = function() remove_calls = remove_calls + 1; error('Windows remove failure') end

    assert(h.messages['set'] ~= nil, 'set message not registered')
    -- 1. File already present
    h.messages['set']('accent', 'teal')
    eq(rename_calls, 0, 'os.rename should not be called')
    eq(remove_calls, 0, 'os.remove should not be called')

    local f = io.open(conf, 'r')
    local content = f:read('*a')
    f:close()
    local expected1 = {style = 'calm', background = 'dark', accent = 'teal', size = 'comfortable'}
    eq(content, looks.serialize(expected1))

    -- 2. File absent (first save after deleted file)
    orig_remove(conf)
    h.conf_exists = false
    h.messages['set']('style', 'bar')
    eq(rename_calls, 0, 'os.rename should not be called')
    eq(remove_calls, 0, 'os.remove should not be called')

    f = io.open(conf, 'r')
    assert(f ~= nil, 'file should have been created')
    content = f:read('*a')
    f:close()
    local expected2 = {style = 'bar', background = 'dark', accent = 'teal', size = 'comfortable'}
    eq(content, looks.serialize(expected2))

    _G.os.rename = orig_rename
    _G.os.remove = orig_remove
    pcall(orig_remove, conf)
end)

test('open-more closes menu when ui_appearance_more is already open and opens otherwise', function()
    local h = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'})
    dofile(SCRIPT)

    -- Branch 1: menu not open
    h.props['user-data/uosc/menu/type'] = nil
    h.messages['open-more']()
    eq(#h.commands, 1)
    eq(h.commands[1][1], 'script-message-to')
    eq(h.commands[1][2], 'uosc')
    eq(h.commands[1][3], 'open-menu')

    -- Branch 2: ui_appearance_more is open -> close-menu is sent instead
    h.props['user-data/uosc/menu/type'] = 'ui_appearance_more'
    h.messages['open-more']()
    eq(#h.commands, 2)
    eq(h.commands[2][1], 'script-message-to')
    eq(h.commands[2][2], 'uosc')
    eq(h.commands[2][3], 'close-menu')
    eq(h.commands[2][4], 'ui_appearance_more')
end)

-- ── T026: More menu tests (US3) ────────────────────────────────────────

local function build_allowed_command_checker()
    -- 1. config/input.conf.template
    local input_commands = {}
    local f_in = assert(io.open(INPUT_CONF_TEMPLATE, 'r'))
    for line in f_in:lines() do
        local trimmed = line:match('^%s*(.-)%s*$')
        if trimmed ~= '' and not trimmed:match('^#') then
            local key, cmd = trimmed:match('^(%S+)%s+(.*)$')
            if cmd then
                cmd = cmd:gsub('^no%-osd%s+', '')
                input_commands[cmd] = true
            end
        end
    end
    f_in:close()

    -- 2. tests/fixtures/uosc-5.13.0/uosc-options.json bindings
    local uosc_bindings = {}
    local f_json = assert(io.open(UOSC_OPTIONS_JSON, 'r'))
    local json_text = f_json:read('*a')
    f_json:close()
    local bindings_block = json_text:match('"bindings"%s*:%s*%[(.-)%]')
    if bindings_block then
        for b in bindings_block:gmatch('"([^"]+)"') do
            uosc_bindings[b] = true
        end
    end

    -- 3. register_script_message in the 4 scripts
    local script_messages = {
        player_toolbar = {},
        profile_picker = {},
        help_overlay = {},
        ui_appearance = {},
    }
    local script_files = {
        player_toolbar = SCRIPT_PLAYER_TOOLBAR,
        profile_picker = SCRIPT_PROFILE_PICKER,
        help_overlay = SCRIPT_HELP_OVERLAY,
        ui_appearance = SCRIPT,
    }
    for sname, spath in pairs(script_files) do
        local sf = assert(io.open(spath, 'r'))
        local scontent = sf:read('*a')
        sf:close()
        for msg in scontent:gmatch('register_script_message%s*%(%s*[\'"]([^\'"]+)[\'"]') do
            script_messages[sname][msg] = true
        end
    end

    -- Checker function
    return function(cmd)
        -- 1. input.conf.template commands
        if input_commands[cmd] then return true end

        -- 2. script-binding uosc/<name>
        local uosc_b = cmd:match('^script%-binding%s+uosc/([%w_%-]+)$')
        if uosc_b and uosc_bindings[uosc_b] then return true end

        -- 3. script-message-to <script> <message> [args]
        local sname, smsg = cmd:match('^script%-message%-to%s+([%w_%-]+)%s+([%w_%-]+)')
        if sname and smsg and script_messages[sname] and script_messages[sname][smsg] then
            return true
        end

        -- 4. extras
        if cmd == 'cycle-values loop-playlist inf no' then return true end
        if cmd == 'cycle-values loop-file inf no' then return true end
        if cmd == 'script-binding ytdl_sub_menu/open' then return true end
        if cmd == 'script-binding smart_paste/paste-to-open' then return true end
        if cmd:match('^set%s+speed%s+%-?%d+%.?%d*$') then return true end

        return false
    end
end

test('all More menu row commands are in the allowed set (SC-005)', function()
    local checker = build_allowed_command_checker()
    local full_state = {
        is_stream = true,
        video_tracks = 2,
        editions = 2,
        speed = 1.0,
        loop_playlist = 'no',
        loop_file = 'no',
        shuffle = false,
        anime4k_mode = 'A+A',
        stable_volume = false,
    }
    local menu = looks.more_menu(looks.DEFAULTS, full_state)
    local function collect_commands(items, out)
        out = out or {}
        for _, it in ipairs(items) do
            if it.value then
                out[#out + 1] = it.value
            end
            if it.items then
                collect_commands(it.items, out)
            end
        end
        return out
    end
    local commands = collect_commands(menu.items)
    assert(#commands >= 25, 'expected full menu commands count >= 25, got ' .. tostring(#commands))
    for _, cmd in ipairs(commands) do
        assert(checker(cmd), 'Command not in SC-005 allowed set: ' .. tostring(cmd))
    end
end)

test('Anime4K mode rows use the 8 modes in order with MODE_LABELS from profile_picker', function()
    local f = assert(io.open(SCRIPT_PROFILE_PICKER, 'r'))
    local content = f:read('*a')
    f:close()
    local labels_block = content:match('local MODE_LABELS = %{([^%}]*)%}')
    assert(labels_block ~= nil, 'MODE_LABELS block not found in profile_picker.lua')
    local expected_labels = {}
    for k, v in labels_block:gmatch('%["([^"]+)"%]%s*=%s*"([^"]+)"') do
        expected_labels[k] = v
    end

    local expected_order = {'off', 'fast', 'A', 'B', 'C', 'A+A', 'B+B', 'C+A'}
    eq(#expected_order, 8)

    local menu = looks.more_menu(looks.DEFAULTS, {anime4k_mode = 'A'})
    local pic_sound
    for _, it in ipairs(menu.items) do
        if it.title == 'Picture & sound' then pic_sound = it break end
    end
    assert(pic_sound ~= nil, 'Picture & sound item not found')

    local anime_item
    for _, it in ipairs(pic_sound.items) do
        if it.title == 'Anime4K mode' then anime_item = it break end
    end
    assert(anime_item ~= nil, 'Anime4K mode item not found')
    eq(#anime_item.items, 8)

    for i, mode in ipairs(expected_order) do
        local row = anime_item.items[i]
        eq(row.title, mode, 'mode title at ' .. tostring(i))
        eq(row.value, 'script-message-to profile_picker set-mode ' .. mode)
        if mode == 'A' then
            eq(row.active, true)
            eq(row.hint, nil, 'active mode must not have hint')
        else
            eq(row.active, nil)
            eq(row.hint, expected_labels[mode], 'hint for mode ' .. mode)
        end
    end
end)

test('conditional rows: stream quality and download video only when is_stream (FR-019)', function()
    -- local file: no stream quality, no download video
    local local_menu = looks.more_menu(looks.DEFAULTS, {is_stream = false})
    for _, it in ipairs(local_menu.items) do
        assert(it.title ~= 'Stream quality', 'Stream quality must not appear for local files')
        if it.title == 'Open' then
            for _, sub in ipairs(it.items) do
                assert(sub.title ~= 'Download video', 'Download video must not appear for local files')
            end
        end
    end

    -- stream: has stream quality and download video
    local stream_menu = looks.more_menu(looks.DEFAULTS, {is_stream = true})
    local has_quality, has_download = false, false
    for idx, it in ipairs(stream_menu.items) do
        if it.title == 'Stream quality' then
            has_quality = true
            eq(idx, 4, 'Stream quality should be after Audio')
            eq(it.value, 'script-message-to player_toolbar open-quality-menu')
        end
        if it.title == 'Open' then
            for _, sub in ipairs(it.items) do
                if sub.title == 'Download video' then
                    has_download = true
                    eq(sub.value, 'script-message-to player_toolbar download-video')
                end
            end
        end
    end
    assert(has_quality, 'Stream quality must appear for streams')
    assert(has_download, 'Download video must appear in Open for streams')
end)

test('conditional rows: video track only when video_tracks > 1, editions only when editions > 1', function()
    -- 1 video track + 1 album art track -> video_tracks = 1 -> no Video track
    local menu1 = looks.more_menu(looks.DEFAULTS, {video_tracks = 1, editions = 1})
    local pic_sound1
    for _, it in ipairs(menu1.items) do
        if it.title == 'Picture & sound' then pic_sound1 = it break end
    end
    for _, sub in ipairs(pic_sound1.items) do
        assert(sub.title ~= 'Video track', 'Video track should not appear when video_tracks <= 1')
        assert(sub.title ~= 'Editions', 'Editions should not appear when editions <= 1')
    end

    -- 2 video tracks, 2 editions -> both appear
    local menu2 = looks.more_menu(looks.DEFAULTS, {video_tracks = 2, editions = 2})
    local pic_sound2
    for _, it in ipairs(menu2.items) do
        if it.title == 'Picture & sound' then pic_sound2 = it break end
    end
    local has_vt, has_ed = false, false
    for _, sub in ipairs(pic_sound2.items) do
        if sub.title == 'Video track' then
            has_vt = true
            eq(sub.value, 'script-binding uosc/video')
        end
        if sub.title == 'Editions' then
            has_ed = true
            eq(sub.value, 'script-binding uosc/editions')
        end
    end
    assert(has_vt, 'Video track should appear when video_tracks > 1')
    assert(has_ed, 'Editions should appear when editions > 1')
end)

test('marks: active rows have no hint; Loop, Speed, Stable volume marked from state', function()
    local state = {
        loop_playlist = 'inf',
        loop_file = 'no',
        speed = 1.2504, -- within 0.001 tolerance of 1.25
        stable_volume = true,
        shuffle = true,
        anime4k_mode = 'off',
    }
    local menu = looks.more_menu(looks.DEFAULTS, state)
    local playback, pic_sound
    for _, it in ipairs(menu.items) do
        if it.title == 'Playback' then playback = it end
        if it.title == 'Picture & sound' then pic_sound = it end
    end
    assert(playback ~= nil and pic_sound ~= nil)

    -- Playback: Shuffle
    local shuffle_item
    for _, sub in ipairs(playback.items) do
        if sub.title == 'Shuffle' then shuffle_item = sub break end
    end
    assert(shuffle_item ~= nil)
    eq(shuffle_item.active, true)
    eq(shuffle_item.hint, nil)
    eq(shuffle_item.keep_open, true)

    -- Playback: Loop playlist (active)
    local loop_pl_item
    for _, sub in ipairs(playback.items) do
        if sub.title == 'Loop playlist' then loop_pl_item = sub break end
    end
    assert(loop_pl_item ~= nil)
    eq(loop_pl_item.active, true)
    eq(loop_pl_item.hint, nil)
    eq(loop_pl_item.keep_open, true)

    -- Playback: Loop file (inactive)
    local loop_f_item
    for _, sub in ipairs(playback.items) do
        if sub.title == 'Loop file' then loop_f_item = sub break end
    end
    assert(loop_f_item ~= nil)
    eq(loop_f_item.active, nil)
    eq(loop_f_item.keep_open, true)

    -- Playback: Speed
    local speed_sub
    for _, sub in ipairs(playback.items) do
        if sub.title == 'Speed' then speed_sub = sub break end
    end
    assert(speed_sub ~= nil)
    local speed_vals = {'0.5×', '0.75×', '1×', '1.25×', '1.5×', '1.75×', '2×'}
    local speed_nums = {0.5, 0.75, 1, 1.25, 1.5, 1.75, 2}
    eq(#speed_sub.items, #speed_vals)
    for i, s_title in ipairs(speed_vals) do
        local it = speed_sub.items[i]
        eq(it.title, s_title)
        eq(it.value, 'set speed ' .. tostring(speed_nums[i]))
        if s_title == '1.25×' then
            eq(it.active, true)
            eq(it.hint, nil)
        else
            eq(it.active, nil)
        end
    end

    -- Picture & sound: Stable volume
    local sv_item
    for _, sub in ipairs(pic_sound.items) do
        if sub.title == 'Stable volume' then sv_item = sub break end
    end
    assert(sv_item ~= nil)
    eq(sv_item.active, true)
    eq(sv_item.hint, nil)
    eq(sv_item.keep_open, true)
end)

test('a change of a marked value sends update-menu with the new mark', function()
    local h = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'})
    dofile(SCRIPT)
    for _, prop in ipairs({'loop-playlist', 'loop-file', 'speed', 'user-data/anime4k/mode',
        'user-data/player_toolbar/stable-volume'}) do
        assert(h.observers[prop] ~= nil, prop .. ' is not observed')
    end
    h.props['loop-file'] = 'inf'
    local before = #h.commands
    h.observers['loop-file']('loop-file', 'inf')
    eq(#h.commands, before + 1, 'one command sent')
    local cmd = h.commands[#h.commands]
    eq(cmd[3], 'update-menu')
    local menu = require('mp.utils').parse_json(cmd[4])
    local loop_file
    for _, it in ipairs(menu.items) do
        if it.title == 'Playback' then
            for _, sub in ipairs(it.items) do
                if sub.title == 'Loop file' then loop_file = sub end
            end
        end
    end
    assert(loop_file and loop_file.active == true, 'Loop file is not marked after the change')
end)

test('toggle-shuffle runs script-binding uosc/shuffle, flips mark and sends update-menu', function()
    local h = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'})
    dofile(SCRIPT)

    assert(h.messages['toggle-shuffle'] ~= nil, 'toggle-shuffle message not registered')

    local cmds_before = #h.commands
    h.messages['toggle-shuffle']()

    -- Runs script-binding uosc/shuffle
    eq(h.commands[cmds_before + 1][1], 'script-binding')
    eq(h.commands[cmds_before + 1][2], 'uosc/shuffle')

    -- Sends update-menu
    local update_cmd = h.commands[cmds_before + 2]
    eq(update_cmd[1], 'script-message-to')
    eq(update_cmd[2], 'uosc')
    eq(update_cmd[3], 'update-menu')

    local utils = require 'mp.utils'
    local menu1 = utils.parse_json(update_cmd[4])
    local shuffle1
    for _, it in ipairs(menu1.items) do
        if it.title == 'Playback' then
            for _, sub in ipairs(it.items) do
                if sub.title == 'Shuffle' then shuffle1 = sub break end
            end
        end
    end
    assert(shuffle1 ~= nil)
    eq(shuffle1.active, true)

    -- Toggle again flips to false
    h.messages['toggle-shuffle']()
    local update_cmd2 = h.commands[#h.commands]
    local menu2 = utils.parse_json(update_cmd2[4])
    local shuffle2
    for _, it in ipairs(menu2.items) do
        if it.title == 'Playback' then
            for _, sub in ipairs(it.items) do
                if sub.title == 'Shuffle' then shuffle2 = sub break end
            end
        end
    end
    assert(shuffle2 ~= nil)
    eq(shuffle2.active, nil)
end)

test('initial shuffle flag starts as true when uosc.conf ends with shuffle=yes, false otherwise', function()
    -- 1. uosc.conf with shuffle=yes
    local uosc_conf_yes = sandbox_conf("# uosc options\nshuffle=no\nshuffle=yes\n")
    local h1 = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'}, {}, nil, uosc_conf_yes)
    dofile(SCRIPT)

    h1.messages['open-more']()
    local utils = require 'mp.utils'
    local menu1 = utils.parse_json(h1.commands[#h1.commands][4])
    local shuf1
    for _, it in ipairs(menu1.items) do
        if it.title == 'Playback' then
            for _, sub in ipairs(it.items) do
                if sub.title == 'Shuffle' then shuf1 = sub break end
            end
        end
    end
    assert(shuf1 ~= nil)
    eq(shuf1.active, true)
    pcall(os.remove, uosc_conf_yes)

    -- 2. uosc.conf with shuffle=no
    local uosc_conf_no = sandbox_conf("shuffle=yes\n# commented\nshuffle=no\n")
    local h2 = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'}, {}, nil, uosc_conf_no)
    dofile(SCRIPT)
    h2.messages['open-more']()
    local menu2 = utils.parse_json(h2.commands[#h2.commands][4])
    local shuf2
    for _, it in ipairs(menu2.items) do
        if it.title == 'Playback' then
            for _, sub in ipairs(it.items) do
                if sub.title == 'Shuffle' then shuf2 = sub break end
            end
        end
    end
    assert(shuf2 ~= nil)
    eq(shuf2.active, nil)
    pcall(os.remove, uosc_conf_no)

    -- 3. missing uosc.conf
    local h3 = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'}, {}, nil, nil)
    dofile(SCRIPT)
    h3.messages['open-more']()
    local menu3 = utils.parse_json(h3.commands[#h3.commands][4])
    local shuf3
    for _, it in ipairs(menu3.items) do
        if it.title == 'Playback' then
            for _, sub in ipairs(it.items) do
                if sub.title == 'Shuffle' then shuf3 = sub break end
            end
        end
    end
    assert(shuf3 ~= nil)
    eq(shuf3.active, nil)
end)

test('open-more and update-menu read state dynamically from mp properties', function()
    local h = create_script_harness({style = 'calm', background = 'dark', accent = 'amber', size = 'comfortable'})
    h.props['demuxer-via-network'] = true
    h.props['speed'] = 1.5
    h.props['loop-playlist'] = 'inf'
    h.props['loop-file'] = 'inf'
    h.props['user-data/anime4k/mode'] = 'B+B'
    h.props['user-data/player_toolbar/stable-volume'] = true
    h.props['edition-list'] = {{id = 0}, {id = 1}}
    h.props['track-list'] = {
        {type = 'video'},
        {type = 'video', albumart = true},
        {type = 'video'},
    }
    dofile(SCRIPT)

    h.messages['open-more']()
    local utils = require 'mp.utils'
    local menu = utils.parse_json(h.commands[#h.commands][4])

    -- Verify stream quality and download video exist
    local has_sq, has_dv, has_ed, has_vt = false, false, false, false
    for _, it in ipairs(menu.items) do
        if it.title == 'Stream quality' then has_sq = true end
        if it.title == 'Open' then
            for _, sub in ipairs(it.items) do
                if sub.title == 'Download video' then has_dv = true end
            end
        end
        if it.title == 'Picture & sound' then
            for _, sub in ipairs(it.items) do
                if sub.title == 'Editions' then has_ed = true end
                if sub.title == 'Video track' then has_vt = true end
                if sub.title == 'Anime4K mode' then
                    for _, m in ipairs(sub.items) do
                        if m.title == 'B+B' then eq(m.active, true) end
                    end
                end
                if sub.title == 'Stable volume' then eq(sub.active, true) end
            end
        end
        if it.title == 'Playback' then
            for _, sub in ipairs(it.items) do
                if sub.title == 'Loop playlist' then eq(sub.active, true) end
                if sub.title == 'Loop file' then eq(sub.active, true) end
                if sub.title == 'Speed' then
                    for _, s in ipairs(sub.items) do
                        if s.title == '1.5×' then eq(s.active, true) end
                    end
                end
            end
        end
    end
    assert(has_sq, 'Stream quality should be present')
    assert(has_dv, 'Download video should be present')
    assert(has_ed, 'Editions should be present')
    assert(has_vt, 'Video track should be present (2 real video tracks)')
end)

io.stdout:write(string.format('UI appearance tests passed: %d\n', total))
io.stdout:flush()
