-- scripts/ui_appearance.lua: applies chosen UI style and look at load and opens More menu
local utils = require 'mp.utils'
local msg = require 'mp.msg'
local opt = require 'mp.options'

local looks_path = mp.find_config_file and mp.find_config_file('scripts/modules/looks.lua')
local ok_looks, looks = pcall(dofile, looks_path or '')
if not ok_looks or type(looks) ~= 'table' then
    ok_looks, looks = pcall(dofile, 'scripts/modules/looks.lua')
    if not ok_looks or type(looks) ~= 'table' then
        msg.error('ui_appearance: failed to load looks module')
        return
    end
end

-- 1. Read options with empty defaults
local raw = {style = '', background = '', accent = '', size = ''}
opt.read_options(raw, 'ui_appearance')

-- 2. Normalize and warn on fallbacks
local current_look, fallbacks = looks.normalize(raw)
if #fallbacks > 0 then
    msg.warn('ui_appearance.conf: using defaults for ' .. table.concat(fallbacks, ', '))
end

-- 3. Apply write
local function apply_look(look)
    local current_opts = mp.get_property_native('script-opts') or {}
    local merged_opts = looks.merge_script_opts(current_opts, look)
    mp.set_property_native('script-opts', merged_opts)
end

apply_look(current_look)

-- Path of a file under the config dir's script-opts/, existing or not.
local function opts_file_path(name)
    local rel = 'script-opts/' .. name
    local found = mp.find_config_file and mp.find_config_file(rel)
    if found and found ~= '' then return found end
    if mp.command_native then
        local expanded = mp.command_native({'expand-path', '~~/' .. rel})
        if expanded and expanded ~= '' and not expanded:find('^~~/') then
            return expanded
        end
    end
    local ok_dir, dir = pcall(mp.get_property, 'config-dir')
    dir = (ok_dir and dir) or ''
    if dir ~= '' then
        local sep = dir:sub(-1)
        if sep ~= '/' and sep ~= '\\' then dir = dir .. '/' end
        return dir .. rel
    end
    return nil
end

local function save_look(look)
    local path = opts_file_path('ui_appearance.conf')
    local file, err
    if path then
        file, err = io.open(path, 'w')
    else
        err = 'no config path'
    end
    if not file then
        mp.osd_message('Appearance not saved: ' .. tostring(err), 3)
        return false
    end
    file:write(looks.serialize(look))
    file:close()
    return true
end

local function read_initial_shuffle()
    local path = opts_file_path('uosc.conf')
    if not path then return false end
    local f = io.open(path, 'r')
    if not f then return false end
    local last_val = nil
    for line in f:lines() do
        local val = line:match('^%s*shuffle%s*=%s*(.-)%s*$')
        if val then
            last_val = val
        end
    end
    f:close()
    return last_val == 'yes'
end

local shuffle_flag = read_initial_shuffle()

local function read_state()
    local video_count = 0
    local tracks = mp.get_property_native('track-list') or {}
    for _, t in ipairs(tracks) do
        if t.type == 'video' and not t.image and not t.albumart then
            video_count = video_count + 1
        end
    end
    local editions = mp.get_property_native('edition-list') or {}
    local speed = mp.get_property_native('speed')
    if speed == nil then
        speed = tonumber(mp.get_property('speed'))
    end
    local is_stream = false
    if mp.get_property_bool then
        is_stream = mp.get_property_bool('demuxer-via-network', false)
    else
        is_stream = mp.get_property_native('demuxer-via-network') == true
    end

    return {
        loop_playlist = mp.get_property('loop-playlist'),
        loop_file = mp.get_property('loop-file'),
        speed = tonumber(speed) or 1,
        video_tracks = video_count,
        editions = #editions,
        is_stream = is_stream,
        anime4k_mode = mp.get_property_native('user-data/anime4k/mode'),
        stable_volume = mp.get_property_native('user-data/player_toolbar/stable-volume'),
        shuffle = shuffle_flag,
    }
end

local function send_update_menu()
    local state = read_state()
    local menu = looks.more_menu(current_look, state)
    local menu_json = utils.format_json(menu)
    if menu_json then
        pcall(mp.commandv, 'script-message-to', 'uosc', 'update-menu', menu_json)
    end
end

-- Keep the marks of an open More menu current: rows with keep_open run their
-- command through uosc, so the new value arrives here as a property change.
-- uosc ignores update-menu unless a ui_appearance_more menu is open.
for _, prop in ipairs({'loop-playlist', 'loop-file', 'speed', 'user-data/anime4k/mode',
    'user-data/player_toolbar/stable-volume'}) do
    mp.observe_property(prop, 'native', function() send_update_menu() end)
end

-- Register open-more script message
mp.register_script_message('open-more', function()
    local open_menu_type = mp.get_property_native('user-data/uosc/menu/type')
    if open_menu_type == 'ui_appearance_more' then
        pcall(mp.commandv, 'script-message-to', 'uosc', 'close-menu', 'ui_appearance_more')
        return
    end
    local state = read_state()
    local menu = looks.more_menu(current_look, state)
    local menu_json = utils.format_json(menu)
    if menu_json then
        pcall(mp.commandv, 'script-message-to', 'uosc', 'open-menu', menu_json)
    end
end)

-- Register toggle-shuffle script message
mp.register_script_message('toggle-shuffle', function()
    pcall(mp.commandv, 'script-binding', 'uosc/shuffle')
    shuffle_flag = not shuffle_flag
    send_update_menu()
end)

-- Register set script message
mp.register_script_message('set', function(field, value)
    if not field or not looks.CHOICES[field] then
        msg.warn('ui_appearance: unknown appearance field: ' .. tostring(field))
        return
    end
    local allowed = false
    for _, v in ipairs(looks.CHOICES[field]) do
        if v == value then
            allowed = true
            break
        end
    end
    if not allowed then
        msg.warn(string.format('ui_appearance: invalid value %q for %s', tostring(value), field))
        return
    end

    current_look[field] = value

    -- 1. Save first
    save_look(current_look)

    -- 2. Apply write
    apply_look(current_look)

    -- 3. Update menu
    send_update_menu()
end)
