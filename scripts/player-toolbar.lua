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

local policy_path = mp.find_config_file and mp.find_config_file('scripts/modules/stream_policy.lua')
local ok_pol, policy = pcall(dofile, policy_path or '')
if not ok_pol or type(policy) ~= 'table' then
    ok_pol, policy = pcall(dofile, 'scripts/modules/stream_policy.lua')
    if not ok_pol or type(policy) ~= 'table' then policy = nil end
end

local function format_monogram(text)
    if not text or text == '' then return nil end
    local controls_size = (mp.get_opt and tonumber(mp.get_opt('uosc-controls_size'))) or 32
    local fs = math.max(10, math.floor(controls_size * 0.47))
    return string.format('{\\fnSegoe UI\\b1\\fs%d\\fscx95\\fscy95}%s', fs, text)
end

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
    local data = utils.format_json({
        icon = 'graphic_eq', active = active, badge = nil,
        tooltip = 'Stable volume: ' .. (active and 'On' or 'Off'),
        command = {'script-message-to', script, 'toggle-stable-volume'},
    })
    -- Capture only the JSON value, not a codec's secondary status/error return.
    -- uosc may not exist yet; its startup broadcast republishes the button.
    if data then pcall(mp.commandv, 'script-message-to', 'uosc', 'set-button', 'stable-volume', data) end
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

local last_quality_icon
local function quality_monogram(w, h)
    if policy and policy.quality_monogram then
        return policy.quality_monogram(w, h)
    end
    local width = tonumber(w) or 0
    local height = tonumber(h) or 0
    if width <= 0 and height <= 0 then return nil end
    if width >= 3840 or height >= 2160 then return '4K' end
    if width >= 1280 or height >= 720 then return 'HD' end
    return 'SD'
end
local function publish_quality(force)
    local w = mp.get_property_number('width') or mp.get_property_number('dwidth')
    local h = mp.get_property_number('height') or mp.get_property_number('dheight')
    local monogram = quality_monogram(w, h)
    local icon = monogram and format_monogram(monogram) or 'settings'
    if not force and last_quality_icon == icon then return end
    last_quality_icon = icon
    local tooltip = monogram and ('Video quality: ' .. monogram) or 'Video quality'
    local data = utils.format_json({
        icon = icon, badge = nil, tooltip = tooltip,
        command = {'script-message-to', script, 'open-quality-menu'},
    })
    if data then pcall(mp.commandv, 'script-message-to', 'uosc', 'set-button', 'stream-quality', data) end
end
local function open_quality_menu()
    local current_h = mp.get_property_number('height') or mp.get_property_number('dheight') or 0
    local res_data = mp.get_property_native('user-data/mpv/ytdl/json-subprocess-result')
    local formats = nil
    if type(res_data) == 'table' and res_data.status == 0 and type(res_data.stdout) == 'string' then
        local parsed = utils.parse_json(res_data.stdout)
        if type(parsed) == 'table' and type(parsed.formats) == 'table' then
            formats = parsed.formats
        end
    end

    local heights_map = {}
    if formats then
        for _, f in ipairs(formats) do
            if type(f) == 'table' and f.vcodec and f.vcodec ~= 'none' and f.height and f.height > 0 then
                local h = f.height
                local w = f.width or 0
                local fps = f.fps and math.floor(f.fps + 0.5) or nil
                local note = f.format_note
                if not heights_map[h] or (fps and fps > (heights_map[h].fps or 0)) then
                    heights_map[h] = {height = h, width = w, fps = fps, format_note = note}
                end
            end
        end
    end

    local sorted_heights = {}
    for _, info in pairs(heights_map) do
        sorted_heights[#sorted_heights + 1] = info
    end
    table.sort(sorted_heights, function(a, b) return a.height > b.height end)

    if #sorted_heights == 0 then
        for _, h in ipairs({2160, 1440, 1080, 720, 480, 360, 240, 144}) do
            sorted_heights[#sorted_heights + 1] = {height = h}
        end
    end

    local items = {}
    for _, info in ipairs(sorted_heights) do
        local h = info.height
        local label = policy and policy.quality_label and policy.quality_label(info.width, h, info.fps, info.format_note)
        if not label then
            label = (h >= 2160 and '4K (' .. h .. 'p)' or (h .. 'p'))
            if info.fps and info.fps > 30 then
                label = label .. tostring(info.fps)
            end
        end
        local is_current = (current_h > 0 and math.abs(current_h - h) <= 15)
        items[#items + 1] = {
            title = label,
            hint = is_current and 'Current' or nil,
            active = is_current,
            value = {'script-message-to', script, 'set-quality', tostring(h), label},
        }
    end

    local menu_json = utils.format_json({
        type = 'stream_quality_menu',
        title = 'Video quality',
        items = items,
    })
    if menu_json then pcall(mp.commandv, 'script-message-to', 'uosc', 'open-menu', menu_json) end
end
local function set_quality(target_h, target_label)
    local h = tonumber(target_h)
    if not h then return end
    local format = 'bestvideo[height<=?' .. h .. ']+bestaudio/best[height<=?' .. h .. ']'
    mp.set_property('ytdl-format', format)
    local duration = mp.get_property_native('duration')
    local time_pos = mp.get_property('time-pos')
    mp.command('playlist-play-index current')
    if duration and duration > 0 and time_pos then
        local function on_reload()
            mp.unregister_event(on_reload)
            pcall(mp.commandv, 'seek', time_pos, 'absolute')
        end
        mp.register_event('file-loaded', on_reload)
    end
    mp.osd_message('Quality: ' .. (target_label or (h >= 2160 and '4K' or (h .. 'p'))), 2)
end

local clean_lang_names = {
    ar = "Arabic", ja = "Japanese", en = "English", es = "Spanish",
    fr = "French", de = "German", it = "Italian", pt = "Portuguese",
    ru = "Russian", zh = "Chinese", ko = "Korean", hi = "Hindi",
    tr = "Turkish", id = "Indonesian", pl = "Polish", uk = "Ukrainian",
    nl = "Dutch", sv = "Swedish", vi = "Vietnamese", th = "Thai",
    fa = "Persian", he = "Hebrew", el = "Greek", cs = "Czech",
    ro = "Romanian", hu = "Hungarian", da = "Danish", fi = "Finnish",
    no = "Norwegian", sk = "Slovak", ms = "Malay", bn = "Bengali",
    ur = "Urdu", ta = "Tamil", te = "Telugu", mr = "Marathi",
}
local name_to_code = {}
for code, name in pairs(clean_lang_names) do
    name_to_code[name:lower()] = code
end

local function lang_badge(lang, title)
    if type(lang) == 'string' and #lang > 0 then
        local code = lang:lower():gsub('_', '-'):gsub('%-orig$', ''):match('^[a-z]+')
        if code and #code > 0 then
            return code:sub(1, 2):upper()
        end
    end
    if type(title) == 'string' and #title > 0 then
        local lower = title:lower()
        for name, code in pairs(name_to_code) do
            if lower:find(name, 1, true) then
                return code:upper()
            end
        end
    end
    return nil
end

local last_audio_icon
local function publish_audio(force)
    local tracks = mp.get_property_native('track-list') or {}
    local current_aid = mp.get_property_number('current-tracks/audio/id')
    local selected_track = nil
    for _, t in ipairs(tracks) do
        if t.type == 'audio' and (t.selected or (current_aid and t.id == current_aid)) then
            selected_track = t
            break
        end
    end
    local monogram = nil
    local tooltip = 'Audio tracks and dubs'
    if selected_track then
        if policy and policy.monogram then
            monogram = policy.monogram(selected_track.lang, selected_track.title)
        else
            monogram = lang_badge(selected_track.lang, selected_track.title)
        end
        local display_name = nil
        if selected_track.lang then
            local base = selected_track.lang:match('^[a-z]+')
            display_name = clean_lang_names[base]
        end
        if not display_name and selected_track.title and #selected_track.title > 0 then
            display_name = selected_track.title
        end
        if display_name then
            tooltip = 'Audio: ' .. display_name
        end
    end
    local icon = monogram and format_monogram(monogram) or 'headphones'
    if not force and last_audio_icon == icon then return end
    last_audio_icon = icon
    local data = utils.format_json({
        icon = icon,
        badge = nil,
        tooltip = tooltip,
        command = {'script-message-to', script, 'open-audio-menu'},
    })
    if data then pcall(mp.commandv, 'script-message-to', 'uosc', 'set-button', 'audio-tracks', data) end
end

local function open_audio_menu()
    local tracks = mp.get_property_native('track-list') or {}
    local current_aid = mp.get_property_number('current-tracks/audio/id')
    local unique_items = {}
    local seen = {}

    for _, t in ipairs(tracks) do
        if t.type == 'audio' then
            local is_current = t.selected or (current_aid and t.id == current_aid)
            local title = t.title
            local lang = t.lang or ''
            local base_lang = lang:match('^[a-z]+')
            local clean_name = base_lang and clean_lang_names[base_lang] or (lang ~= '' and lang:upper()) or nil

            local display_title = title
            if not display_title or #display_title == 0 then
                display_title = clean_name or ('Track ' .. t.id)
            end

            local dedup_key = (clean_name or lang or 'track') .. '\0' .. (display_title or '')
            local bitrate = tonumber(t['demux-bitrate']) or tonumber(t['hls-bitrate']) or 0

            if not seen[dedup_key] then
                local item = {
                    title = display_title,
                    is_current = is_current,
                    track_id = t.id,
                    bitrate = bitrate,
                }
                seen[dedup_key] = item
                unique_items[#unique_items + 1] = item
            else
                local existing = seen[dedup_key]
                if is_current then
                    existing.is_current = true
                    existing.track_id = t.id
                elseif not existing.is_current and bitrate > existing.bitrate then
                    existing.track_id = t.id
                    existing.bitrate = bitrate
                end
            end
        end
    end

    local items = {}
    for _, entry in ipairs(unique_items) do
        items[#items + 1] = {
            title = entry.title,
            hint = entry.is_current and 'Current' or nil,
            active = entry.is_current,
            value = {'set', 'aid', tostring(entry.track_id)},
        }
    end

    if #items == 0 then
        items[1] = {title = 'No audio tracks available', selectable = false, muted = true}
    end
    local menu_json = utils.format_json({
        type = 'audio_tracks_menu',
        title = 'Audio tracks',
        items = items,
    })
    if menu_json then pcall(mp.commandv, 'script-message-to', 'uosc', 'open-menu', menu_json) end
end

mp.register_script_message('open-audio-menu', open_audio_menu)
mp.register_script_message('open-quality-menu', open_quality_menu)
mp.register_script_message('set-quality', set_quality)

-- uosc broadcasts on startup; also publish now if uosc started first.
mp.register_script_message('uosc-version', function()
    publish(nil, true)
    publish_quality(true)
    publish_audio(true)
end)
mp.observe_property('af', 'native', function(_, filters) publish(filters, false) end)
mp.observe_property('height', 'number', function() publish_quality(false) end)
mp.observe_property('dheight', 'number', function() publish_quality(false) end)
mp.observe_property('width', 'number', function() publish_quality(false) end)
mp.observe_property('dwidth', 'number', function() publish_quality(false) end)
mp.observe_property('track-list', 'native', function() publish_audio(false) end)
mp.observe_property('current-tracks/audio/id', 'number', function() publish_audio(false) end)
mp.observe_property('aid', 'string', function() publish_audio(false) end)
mp.register_event('file-loaded', function()
    publish_quality(true)
    publish_audio(true)
end)
publish(nil, true)
publish_quality(true)
publish_audio(true)
