-- scripts/modules/looks.lua: pure appearance logic and look configurations (spec 006)
local M = {}

local DEFAULTS = {
    style = 'calm',
    background = 'dark',
    accent = 'amber',
    size = 'comfortable',
}

local CHOICES = {
    style = {'calm', 'bar', 'focus'},
    background = {'dark', 'black', 'slate'},
    accent = {'amber', 'teal', 'violet', 'rose', 'white'},
    size = {'comfortable', 'compact'},
}

local OWNED_KEYS = {
    'controls',
    'color',
    'opacity',
    'controls_size',
    'controls_spacing',
    'controls_margin',
    'controls_persistency',
    'timeline_size',
    'progress',
    'progress_size',
    'menu_item_height',
}

local OWNED_COLOR_KEYS = {
    'foreground',
    'foreground_text',
    'background',
    'background_text',
    'window_border',
    'curtain',
    'success',
    'error',
    'match',
    'heatmap',
}

local OWNED_OPACITY_KEYS = {
    'timeline',
    'position',
    'chapters',
    'slider',
    'slider_gauge',
    'controls',
    'speed',
    'menu',
    'submenu',
    'border',
    'title',
    'tooltip',
    'thumbnail',
    'curtain',
    'idle_indicator',
    'audio_indicator',
    'buffering_indicator',
    'playlist_position',
    'heatmap',
}

local MORE_UOSC_BINDINGS = {
    'shuffle',
    'video',
    'editions',
    'open-file',
    'menu-blurred',
}

local ACCENT_COLORS = {
    amber = 'f2b544',
    teal = '5eead4',
    violet = 'a78bfa',
    rose = 'fb7185',
    white = 'f2f2f3',
}

local BACKGROUND_COLORS = {
    dark = '0e0f12',
    black = '000000',
    slate = '1c2430',
}

local FIXED_COLORS = {
    foreground_text = '000000',
    background_text = 'f2f2f3',
    window_border = '000000',
    curtain = '06080d',
    success = '34d399',
    error = 'f87171',
    match = '38bdf8',
    heatmap = '00adee',
}

local PLAY = 'cycle:pause_circle:pause:no=pause_circle/yes=play_circle?Play/pause'
local SUBS = 'command:closed_caption:script-binding ytdl_sub_menu/open?Subtitles'
local COND = '<has_many_video>video,<has_many_edition>editions,<stream>button:stream-quality,<stream>button:download-video'
local MORE = 'command:menu:script-message-to ui_appearance open-more?More'

local STYLES = {
    calm = {
        controls = 'prev,' .. PLAY .. ',next,space,<video,audio>speed,' .. SUBS .. ',button:audio-tracks,' .. COND .. ',items,' .. MORE .. ',fullscreen',
        controls_persistency = 'idle',
        opacity_controls = '0',
        progress = 'always',
        progress_size = '3',
        menu_item_height = '40',
    },
    bar = {
        controls = 'prev,' .. PLAY .. ',next,space,<video,audio>speed,' .. SUBS .. ',button:audio-tracks,' .. COND .. ',items,' .. MORE .. ',fullscreen',
        controls_persistency = 'idle,windowed',
        opacity_controls = '0.93',
        progress = 'always',
        progress_size = '3',
        menu_item_height = '40',
    },
    focus = {
        controls = 'space,prev,' .. PLAY .. ',next,space,items,' .. MORE .. ',fullscreen',
        controls_persistency = 'idle',
        opacity_controls = '0',
        progress = 'always',
        progress_size = '3',
        menu_item_height = '40',
    },
}

local SIZES = {
    comfortable = {
        controls_size = '44',
        controls_spacing = '4',
        controls_margin = '8',
        timeline_size = '40',
    },
    compact = {
        controls_size = '36',
        controls_spacing = '2',
        controls_margin = '6',
        timeline_size = '32',
    },
}

local FIXED_OPACITIES = {
    timeline = '0.95',
    position = '1',
    chapters = '0.8',
    slider = '0.95',
    slider_gauge = '1',
    speed = '0.7',
    menu = '0.95',
    submenu = '0.5',
    border = '1',
    title = '1',
    tooltip = '1',
    thumbnail = '1',
    curtain = '0.85',
    idle_indicator = '0.85',
    audio_indicator = '0.6',
    buffering_indicator = '0.4',
    playlist_position = '0.8',
    heatmap = '0.4',
}

local function normalize(raw)
    local raw_map = type(raw) == 'table' and raw or {}
    local look = {}
    local fallbacks = {}
    local fields = {'style', 'background', 'accent', 'size'}

    for _, field in ipairs(fields) do
        local val = raw_map[field]
        local valid = false
        if type(val) == 'string' and val ~= '' then
            for _, allowed in ipairs(CHOICES[field]) do
                if val == allowed then
                    valid = true
                    break
                end
            end
        end
        if valid then
            look[field] = val
        else
            look[field] = DEFAULTS[field]
            fallbacks[#fallbacks + 1] = field
        end
    end

    return look, fallbacks
end

local function uosc_options(look)
    local validated_look = normalize(look)
    local style = STYLES[validated_look.style]
    local size = SIZES[validated_look.size]
    local acc_color = ACCENT_COLORS[validated_look.accent]
    local bg_color = BACKGROUND_COLORS[validated_look.background]

    local color_parts = {}
    for _, ck in ipairs(OWNED_COLOR_KEYS) do
        local val
        if ck == 'foreground' then
            val = acc_color
        elseif ck == 'background' then
            val = bg_color
        else
            val = FIXED_COLORS[ck]
        end
        color_parts[#color_parts + 1] = ck .. '=' .. val
    end
    local color_str = table.concat(color_parts, ',')

    local opac_parts = {}
    for _, ok in ipairs(OWNED_OPACITY_KEYS) do
        local val
        if ok == 'controls' then
            val = style.opacity_controls
        else
            val = FIXED_OPACITIES[ok]
        end
        opac_parts[#opac_parts + 1] = ok .. '=' .. val
    end
    local opac_str = table.concat(opac_parts, ',')

    return {
        ['uosc-controls'] = style.controls,
        ['uosc-color'] = color_str,
        ['uosc-opacity'] = opac_str,
        ['uosc-controls_size'] = size.controls_size,
        ['uosc-controls_spacing'] = size.controls_spacing,
        ['uosc-controls_margin'] = size.controls_margin,
        ['uosc-controls_persistency'] = style.controls_persistency,
        ['uosc-timeline_size'] = size.timeline_size,
        ['uosc-progress'] = style.progress,
        ['uosc-progress_size'] = style.progress_size,
        ['uosc-menu_item_height'] = style.menu_item_height,
    }
end

local function merge_script_opts(current, look)
    local merged = {}
    if type(current) == 'table' then
        for k, v in pairs(current) do
            merged[k] = v
        end
    end
    local opts = uosc_options(look)
    for k, v in pairs(opts) do
        merged[k] = v
    end
    return merged
end

local function serialize(look)
    local l = normalize(look)
    return "# Player look, chosen in More > Appearance. Values:\n"
        .. "# style=calm|bar|focus background=dark|black|slate accent=amber|teal|violet|rose|white size=comfortable|compact\n"
        .. "style=" .. l.style .. "\n"
        .. "background=" .. l.background .. "\n"
        .. "accent=" .. l.accent .. "\n"
        .. "size=" .. l.size .. "\n"
end

local function hex_to_rgb(hex)
    local h = hex:gsub('^#', '')
    local r = tonumber(h:sub(1, 2), 16) or 0
    local g = tonumber(h:sub(3, 4), 16) or 0
    local b = tonumber(h:sub(5, 6), 16) or 0
    return r, g, b
end

local function blend(top_hex, alpha, under_hex)
    local tr, tg, tb = hex_to_rgb(top_hex)
    local ur, ug, ub = hex_to_rgb(under_hex)
    local a = tonumber(alpha) or 1
    local r = math.floor(a * tr + (1 - a) * ur + 0.5)
    local g = math.floor(a * tg + (1 - a) * ug + 0.5)
    local b = math.floor(a * tb + (1 - a) * ub + 0.5)
    return string.format('%02x%02x%02x', r, g, b)
end

local function srgb_to_linear(c)
    local v = c / 255.0
    if v <= 0.04045 then
        return v / 12.92
    else
        return ((v + 0.055) / 1.055) ^ 2.4
    end
end

local function relative_luminance(hex)
    local r, g, b = hex_to_rgb(hex)
    return 0.2126 * srgb_to_linear(r) + 0.7152 * srgb_to_linear(g) + 0.0722 * srgb_to_linear(b)
end

local function contrast(fg_hex, bg_hex)
    local l1 = relative_luminance(fg_hex)
    local l2 = relative_luminance(bg_hex)
    local max_l = math.max(l1, l2)
    local min_l = math.min(l1, l2)
    return (max_l + 0.05) / (min_l + 0.05)
end

local function more_menu(look, state)
    local validated_look = normalize(look)
    local field_order = {'style', 'background', 'accent', 'size'}
    local field_labels = {
        style = 'Style',
        background = 'Background',
        accent = 'Accent',
        size = 'Size',
    }

    local app_items = {}
    for _, field in ipairs(field_order) do
        local choices = CHOICES[field]
        local sub_items = {}
        for _, val in ipairs(choices) do
            local item = {
                title = val,
                value = 'script-message-to ui_appearance set ' .. field .. ' ' .. val,
                keep_open = true,
            }
            if val == validated_look[field] then
                item.active = true
            end
            sub_items[#sub_items + 1] = item
        end
        app_items[#app_items + 1] = {
            title = field_labels[field],
            items = sub_items,
        }
    end

    local items = {
        {
            title = 'Appearance',
            items = app_items,
        },
        {
            title = 'Paste link',
            hint = 'Ctrl+V',
            value = 'script-binding smart_paste/paste-to-open',
        },
        {
            title = 'Stable volume',
            value = 'script-message-to player_toolbar toggle-stable-volume',
        },
        {
            title = 'Full uosc menu',
            value = 'script-binding uosc/menu-blurred',
        },
        {
            title = 'All shortcuts',
            hint = 'F9',
            value = 'script-message-to help_overlay help',
        },
    }
    return {
        type = 'ui_appearance_more',
        title = 'More',
        items = items,
    }
end

M.DEFAULTS = DEFAULTS
M.CHOICES = CHOICES
M.OWNED_KEYS = OWNED_KEYS
M.OWNED_COLOR_KEYS = OWNED_COLOR_KEYS
M.OWNED_OPACITY_KEYS = OWNED_OPACITY_KEYS
M.MORE_UOSC_BINDINGS = MORE_UOSC_BINDINGS
M.ACCENT_COLORS = ACCENT_COLORS
M.BACKGROUND_COLORS = BACKGROUND_COLORS
M.TEXT_COLOR = FIXED_COLORS.background_text
M.BAR_BOX_OPACITY = tonumber(STYLES.bar.opacity_controls)
M.normalize = normalize
M.uosc_options = uosc_options
M.merge_script_opts = merge_script_opts
M.serialize = serialize
M.blend = blend
M.contrast = contrast
M.more_menu = more_menu

return M
