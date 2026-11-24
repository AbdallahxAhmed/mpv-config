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

local function create_script_harness(raw_opts, script_opts)
    local h = {
        props = {
            ['script-opts'] = script_opts or {},
        },
        warnings = {},
        commands = {},
        messages = {},
        set_property_native_calls = 0,
    }
    _G.mp = {
        log = function() end,
        msg = {
            warn = function(msg) h.warnings[#h.warnings + 1] = msg end,
            info = function() end,
            debug = function() end,
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
        commandv = function(...)
            h.commands[#h.commands + 1] = { ... }
        end,
        register_script_message = function(name, fn)
            h.messages[name] = fn
        end,
        find_config_file = function(path)
            if path == 'scripts/modules/looks.lua' then
                return LOOKS_MODULE
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

test('open-more sends one script-message-to uosc open-menu with P1 rows', function()
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
    eq(#menu.items, 4)

    eq(menu.items[1].title, 'Paste link')
    eq(menu.items[1].hint, 'Ctrl+V')
    eq(menu.items[1].value, 'script-binding smart_paste/paste-to-open')

    eq(menu.items[2].title, 'Stable volume')
    eq(menu.items[2].value, 'script-message-to player_toolbar toggle-stable-volume')

    eq(menu.items[3].title, 'Full uosc menu')
    eq(menu.items[3].value, 'script-binding uosc/menu-blurred')

    eq(menu.items[4].title, 'All shortcuts')
    eq(menu.items[4].hint, 'F9')
    eq(menu.items[4].value, 'script-message-to help_overlay help')
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

io.stdout:write(string.format('UI appearance tests passed: %d\n', total))
io.stdout:flush()
