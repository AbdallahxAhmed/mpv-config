-- scripts/more_menu.lua: More menu for uosc toolbar (spec 006)
local utils = require 'mp.utils'

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

local function build_menu(state)
    local items = {
        {
            title = 'Paste link',
            hint = 'Ctrl+V',
            value = 'script-binding smart_paste/paste-to-open',
        },
    }

    if state.is_stream == true then
        items[#items + 1] = {
            title = 'Download video',
            value = 'script-message-to player_toolbar download-video',
        }
    end

    local stable_vol_item = {
        title = 'Stable volume',
        value = 'script-message-to player_toolbar toggle-stable-volume',
        keep_open = true,
    }
    if state.stable_volume == true then
        stable_vol_item.active = true
    end
    items[#items + 1] = stable_vol_item

    local shuffle_item = {
        title = 'Shuffle',
        value = 'script-message-to more_menu toggle-shuffle',
        keep_open = true,
    }
    if state.shuffle == true then
        shuffle_item.active = true
    end
    items[#items + 1] = shuffle_item

    local loop_playlist_item = {
        title = 'Loop playlist',
        value = 'cycle-values loop-playlist inf no',
        keep_open = true,
    }
    if state.loop_playlist and state.loop_playlist ~= 'no' then
        loop_playlist_item.active = true
    end
    items[#items + 1] = loop_playlist_item

    local loop_file_item = {
        title = 'Loop file',
        value = 'cycle-values loop-file inf no',
        keep_open = true,
    }
    if state.loop_file and state.loop_file ~= 'no' then
        loop_file_item.active = true
    end
    items[#items + 1] = loop_file_item

    if (state.editions or 0) > 1 then
        items[#items + 1] = {
            title = 'Editions',
            value = 'script-binding uosc/editions',
        }
    end

    items[#items + 1] = {
        title = 'Full uosc menu',
        value = 'script-binding uosc/menu-blurred',
    }

    items[#items + 1] = {
        title = 'All shortcuts',
        hint = 'F9',
        value = 'script-message-to help_overlay help',
    }

    return {
        type = 'more_menu',
        title = 'More',
        items = items,
    }
end

local function read_state()
    local editions = mp.get_property_native('edition-list') or {}
    local is_stream = false
    if mp.get_property_bool then
        is_stream = mp.get_property_bool('demuxer-via-network', false)
    else
        is_stream = mp.get_property_native('demuxer-via-network') == true
    end

    return {
        is_stream = is_stream,
        stable_volume = mp.get_property_native('user-data/player_toolbar/stable-volume'),
        shuffle = shuffle_flag,
        loop_playlist = mp.get_property('loop-playlist'),
        loop_file = mp.get_property('loop-file'),
        editions = #editions,
    }
end

local function send_update_menu()
    local state = read_state()
    local menu = build_menu(state)
    local menu_json = utils.format_json(menu)
    if menu_json then
        pcall(mp.commandv, 'script-message-to', 'uosc', 'update-menu', menu_json)
    end
end

for _, prop in ipairs({'loop-playlist', 'loop-file', 'user-data/player_toolbar/stable-volume'}) do
    mp.observe_property(prop, 'native', function() send_update_menu() end)
end

mp.register_script_message('open', function()
    local open_menu_type = mp.get_property_native('user-data/uosc/menu/type')
    if open_menu_type == 'more_menu' then
        pcall(mp.commandv, 'script-message-to', 'uosc', 'close-menu', 'more_menu')
        return
    end
    local state = read_state()
    local menu = build_menu(state)
    local menu_json = utils.format_json(menu)
    if menu_json then
        pcall(mp.commandv, 'script-message-to', 'uosc', 'open-menu', menu_json)
    end
end)

mp.register_script_message('toggle-shuffle', function()
    pcall(mp.commandv, 'script-binding', 'uosc/shuffle')
    shuffle_flag = not shuffle_flag
    send_update_menu()
end)

local M = {
    build_menu = build_menu,
    read_state = read_state,
    read_initial_shuffle = read_initial_shuffle,
}
_G.more_menu = M
return M
