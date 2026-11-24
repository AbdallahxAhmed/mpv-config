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
local current_opts = mp.get_property_native('script-opts') or {}
local merged_opts = looks.merge_script_opts(current_opts, current_look)
mp.set_property_native('script-opts', merged_opts)

-- Register open-more script message
mp.register_script_message('open-more', function()
    local menu = looks.more_menu(current_look)
    local menu_json = utils.format_json(menu)
    if menu_json then
        pcall(mp.commandv, 'script-message-to', 'uosc', 'open-menu', menu_json)
    end
end)
