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

local function conf_file_path()
    local found = mp.find_config_file and mp.find_config_file('script-opts/ui_appearance.conf')
    if found and found ~= '' then return found end
    if mp.command_native then
        local expanded = mp.command_native({'expand-path', '~~/script-opts/ui_appearance.conf'})
        if expanded and expanded ~= '' and not expanded:find('^~~/') then
            return expanded
        end
    end
    local ok_dir, dir = pcall(mp.get_property, 'config-dir')
    dir = (ok_dir and dir) or ''
    if dir ~= '' then
        local sep = dir:sub(-1)
        if sep ~= '/' and sep ~= '\\' then dir = dir .. '/' end
        return dir .. 'script-opts/ui_appearance.conf'
    end
    return nil
end

local function save_look(look)
    local path = conf_file_path()
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

-- Register open-more script message
mp.register_script_message('open-more', function()
    local open_menu_type = mp.get_property_native('user-data/uosc/menu/type')
    if open_menu_type == 'ui_appearance_more' then
        pcall(mp.commandv, 'script-message-to', 'uosc', 'close-menu', 'ui_appearance_more')
        return
    end
    local menu = looks.more_menu(current_look)
    local menu_json = utils.format_json(menu)
    if menu_json then
        pcall(mp.commandv, 'script-message-to', 'uosc', 'open-menu', menu_json)
    end
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
    local menu = looks.more_menu(current_look)
    local menu_json = utils.format_json(menu)
    if menu_json then
        pcall(mp.commandv, 'script-message-to', 'uosc', 'update-menu', menu_json)
    end
end)
