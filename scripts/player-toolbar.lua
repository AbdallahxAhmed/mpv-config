-- Mouse-first uosc Stable Volume button. No keypress emulation or polling.
-- Only this named preset (or the exact legacy F8 pair) is changed.
local utils = require 'mp.utils'
local msg = require 'mp.msg'
local script = mp.get_script_name()
local label = 'mpv_config_stable_volume'
local normalizer = 'dynaudnorm=f=500:g=15:p=0.95:m=10'
local limiter = 'alimiter=limit=0.9:level=false'
local graph = normalizer .. ',' .. limiter
local last_active

local function has_graph(filter, expected)
    return type(filter) == 'table' and filter.name == 'lavfi'
        and type(filter.params) == 'table' and filter.params.graph == expected
end
local function legacy(filter, expected)
    return has_graph(filter, expected) and (not filter.label or filter.label == '')
end
local function inspect(filters)
    local preset, active, collision = {}, false, false
    for i, filter in ipairs(filters) do
        if filter.label == label then
            if has_graph(filter, graph) then
                preset[i] = true
                active = active or filter.enabled ~= false
            else
                collision = true
            end
        end
        -- Recognize only the adjacent, unlabelled pair from the shipped F8 preset.
        if legacy(filter, normalizer) and legacy(filters[i + 1], limiter) then
            preset[i], preset[i + 1] = true, true
            active = active or (filter.enabled ~= false and filters[i + 1].enabled ~= false)
        end
    end
    return preset, active, collision
end
local function publish(filters, force)
    filters = type(filters) == 'table' and filters or mp.get_property_native('af', {})
    local _, active = inspect(filters)
    if not force and last_active == active then return end
    last_active = active
    mp.commandv('script-message-to', 'uosc', 'set-button', 'stable-volume', utils.format_json({
        icon = 'compress', active = active, badge = active and 'ON' or '',
        tooltip = 'Stable volume: ' .. (active and 'On' or 'Off'),
        command = {'script-message-to', script, 'toggle-stable-volume'},
    }))
end
local function toggle()
    local filters = mp.get_property_native('af', {})
    local preset, active, collision = inspect(filters)
    if not active and collision then
        mp.osd_message('Stable volume is unavailable: its filter name is already in use.', 4)
        return
    end
    local updated = {}
    for i, filter in ipairs(filters) do
        if not preset[i] then updated[#updated + 1] = filter end
    end
    if not active then
        updated[#updated + 1] = {name = 'lavfi', label = label, enabled = true, params = {graph = graph}}
    end
    local success, err = mp.set_property_native('af', updated)
    if not success then
        mp.osd_message("Stable volume couldn't be changed.", 3)
        msg.warn('Stable volume update failed: ' .. tostring(err))
        return
    end
    publish(nil, true)
    mp.osd_message('Stable volume: ' .. (active and 'Off' or 'On'), 2)
end
mp.register_script_message('toggle-stable-volume', toggle)
-- uosc broadcasts on startup; also publish now if uosc started first.
mp.register_script_message('uosc-version', function() publish(nil, true) end)
mp.observe_property('af', 'native', function(_, filters) publish(filters, false) end)
publish(nil, true)
