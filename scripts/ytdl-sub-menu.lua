-- On-demand YouTube captions in uosc. Zero extraction/parsing on file-loaded.
-- Cancellable async sub-add: no temp files, shell commands, polling or reloads.
local utils = require 'mp.utils'
local msg = require 'mp.msg'
local options = require 'mp.options'
local script = mp.get_script_name()
local o = {timeout = 30}
options.read_options(o, 'ytdl_sub_menu')
local path = mp.find_config_file('scripts/modules/stream_policy.lua')
local ok, policy = pcall(dofile, path or '')
if not ok or type(policy) ~= 'table' then
    msg.warn('Caption helper missing; using the normal uosc subtitle menu')
    local function fallback() mp.commandv('script-binding', 'uosc/subtitles') end
    mp.add_key_binding(nil, 'open', fallback)
    mp.register_script_message('open', fallback)
    mp.register_script_message('open-menu', fallback)
    return
end
local epoch, revision = 0, 0
local ready, attempted = false, false
local captions, choices, job = nil, {}, nil
local open_menu, select_caption, refresh
local kind_names = {manual = 'Creator captions', automatic = 'Auto-generated', translated = 'Auto-translated'}
local function current_url()
    if not ready then return nil end
    -- user-data is node-valued; its string presentation may be JSON-quoted.
    return policy.youtube_url(mp.get_property_native('user-data/mpv/ytdl/source-url', ''))
        or policy.youtube_url(mp.get_property('path', ''))
end
local function cancel_job()
    local old = job
    job = nil
    if old then
        if old.timer then old.timer:kill() end
        if old.id then mp.abort_async_command(old.id) end
    end
end
local function reset()
    epoch, revision = epoch + 1, revision + 1
    ready, attempted = false, false
    captions, choices = nil, {}
    cancel_job()
end
mp.register_event('start-file', reset)
mp.register_event('end-file', reset)
mp.register_event('shutdown', reset)
mp.register_event('file-loaded', function() ready = true end)
local function parse_captions(stdout)
    if type(stdout) ~= 'string' or #stdout > 16 * 1024 * 1024 then return nil end
    local data = utils.parse_json(stdout)
    if type(data) ~= 'table' or data._type == 'playlist' then return nil end
    return policy.captions(data, mp.get_property_native('slang', {'ar', 'en'}))
end
local function cached_captions()
    if not captions and not attempted then
        attempted = true
        local result = mp.get_property_native('user-data/mpv/ytdl/json-subprocess-result')
        if type(result) == 'table' and result.status == 0 then captions = parse_captions(result.stdout) end
    end
    return captions or {}
end
local function start_async(command, label, callback)
    cancel_job()
    local request = {epoch = epoch, url = current_url(), label = label}
    job = request
    request.id = mp.command_native_async(command, function(success, result, err)
        if job ~= request or epoch ~= request.epoch or current_url() ~= request.url then return end
        if request.timer then request.timer:kill() end
        job = nil
        callback(success, result, err)
    end)
    if job == request then
        local timeout = tonumber(o.timeout) or 30
        request.timer = mp.add_timeout(math.max(5, math.min(timeout, 120)), function()
            if job ~= request then return end
            cancel_job()
            mp.osd_message('Caption request timed out. Open the menu to retry.', 4)
        end)
    end
end
local function message(name, ...)
    local value = {'script-message-to', script, name}
    for _, arg in ipairs({...}) do value[#value + 1] = tostring(arg) end
    return value
end
local function same_epoch(value) return tonumber(value) == epoch and ready end
local function select_loaded(id, generation)
    if not same_epoch(generation) then return end
    if id == 'no' then cancel_job(); mp.set_property('sid', 'no'); return end
    for _, track in ipairs(mp.get_property_native('track-list', {})) do
        if track.type == 'sub' and tostring(track.id) == tostring(id) then
            cancel_job()
            mp.set_property('sid', tostring(track.id))
            mp.set_property_bool('sub-visibility', true)
            return
        end
    end
    mp.osd_message('That subtitle track is no longer available.', 3)
end
select_caption = function(entry)
    if not current_url() or not entry or not policy.http_url(entry.url) then return end
    for _, track in ipairs(mp.get_property_native('track-list', {})) do
        if track.type == 'sub' and track['external-filename'] == entry.url then
            select_loaded(track.id, epoch)
            return
        end
    end
    if job and job.label == entry.url then return end
    local title = entry.name .. ' - ' .. kind_names[entry.kind]
    mp.osd_message('Loading ' .. title .. '...', 3)
    start_async({'sub-add', entry.url, 'select', title, entry.lang}, entry.url, function(success)
        if success then
            mp.set_property_bool('sub-visibility', true)
            mp.osd_message('Captions on: ' .. title, 3)
        else
            mp.osd_message('Could not load captions. Refresh the list and retry.', 4)
            msg.warn('Caption load failed; URL may have expired or access was denied')
        end
    end)
end
local function find_ytdl()
    local resolved = mp.get_property_native('user-data/mpv/ytdl/path', '')
    if type(resolved) == 'string' and resolved ~= '' then return resolved end
    local configured = mp.get_opt('ytdl_hook-ytdl_path') or mp.get_opt('ytdl_path')
    if configured and utils.file_info(configured) then return configured end
    for _, candidate in ipairs({'C:/Program Files/mpv/yt-dlp/yt-dlp.exe', 'C:/Program Files/mpv/yt-dlp.exe'}) do
        local info = utils.file_info(candidate)
        if info and info.is_file then return candidate end
    end
    return 'yt-dlp'
end
refresh = function(lang)
    local url = current_url()
    if not url then return end
    if job and job.label == 'metadata' then return end
    local args = {find_ytdl(), '--ignore-config', '--skip-download', '--dump-single-json',
        '--no-playlist', '--no-warnings', '--socket-timeout', '10', '--retries', '1', '--extractor-retries', '1'}
    -- Carry only networking/authentication options, never --exec or output options.
    local raw = mp.get_property_native('options/ytdl-raw-options', {})
    for _, key in ipairs({'cookies', 'cookies-from-browser', 'proxy', 'user-agent',
        'referer', 'extractor-args', 'add-headers'}) do
        if type(raw[key]) == 'string' then args[#args + 1], args[#args + 2] = '--' .. key, raw[key] end
    end
    args[#args + 1], args[#args + 2] = '--', url
    mp.osd_message('Refreshing available YouTube captions (playback continues)...', 3)
    start_async({name = 'subprocess', args = args, playback_only = true,
        capture_stdout = true, capture_stderr = true}, 'metadata', function(success, result)
        if not success or type(result) ~= 'table' or result.status ~= 0 then
            mp.osd_message('Could not refresh captions. Check yt-dlp or try again.', 4)
            return
        end
        local available = parse_captions(result.stdout)
        if not available then mp.osd_message('yt-dlp returned invalid caption metadata.', 4); return end
        captions, attempted = available, true
        if lang then
            local entry = policy.preferred_caption(captions, lang)
            if entry then select_caption(entry)
            else mp.osd_message('No captions available for ' .. lang:upper(), 3) end
        else open_menu() end
    end)
end
open_menu = function()
    if not current_url() then mp.commandv('script-binding', 'uosc/subtitles'); return end
    local current = mp.get_property_native('sid')
    local visible = mp.get_property_bool('sub-visibility', true)
    local items = {{title = 'Subtitles off', icon = 'subtitles_off',
        active = current == false or current == 'no' or current == nil,
        value = message('select-loaded', 'no', epoch)}}
    for _, track in ipairs(mp.get_property_native('track-list', {})) do
        if track.type == 'sub' then
            items[#items + 1] = {title = track.title or track.lang or ('Track ' .. track.id),
                hint = (track.lang or '') .. (visible and '' or ' - hidden'), icon = 'subtitles',
                active = tostring(current) == tostring(track.id), value = message('select-loaded', track.id, epoch)}
        end
    end
    revision = revision + 1
    choices = {}
    local groups = {manual = {}, automatic = {}, translated = {}}
    for i, entry in ipairs(cached_captions()) do
        local token = epoch .. ':' .. revision .. ':' .. i
        choices[token] = entry
        local group = groups[entry.kind]
        group[#group + 1] = {title = entry.name, icon = entry.kind == 'translated' and 'translate' or 'subtitles',
            hint = entry.lang:upper() .. ' - ' .. kind_names[entry.kind], value = message('select-caption', token)}
    end
    for _, kind in ipairs({'manual', 'automatic', 'translated'}) do
        if #groups[kind] > 0 then
            items[#items + 1] = {title = kind_names[kind], hint = tostring(#groups[kind]),
                icon = kind == 'translated' and 'translate' or 'subtitles', items = groups[kind]}
        end
    end
    if not next(choices) then
        items[#items + 1] = {title = 'No captions listed in playback metadata',
            hint = 'Use Refresh below; some videos have none', selectable = false}
    end
    if job then
        items[#items + 1] = {title = 'Cancel caption request', icon = 'close', value = message('cancel', epoch)}
    else
        items[#items + 1] = {title = 'Refresh available captions', icon = 'refresh',
            hint = 'Only on request', value = message('refresh', epoch)}
    end
    items[#items + 1] = {title = 'Load a local subtitle file', icon = 'folder_open',
        value = {'script-binding', 'uosc/load-subtitles'}}
    mp.commandv('script-message-to', 'uosc', 'open-menu', utils.format_json({
        type = 'ytdl_sub_menu', title = 'Subtitles / YouTube captions', items = items}))
end
mp.add_key_binding(nil, 'open', open_menu)
mp.register_script_message('open', open_menu)
mp.register_script_message('open-menu', open_menu)
mp.register_script_message('select-loaded', select_loaded)
mp.register_script_message('select-caption', function(token) select_caption(choices[token]) end)
mp.register_script_message('refresh', function(generation) if same_epoch(generation) then refresh() end end)
mp.register_script_message('cancel', function(generation) if same_epoch(generation) then cancel_job() end end)
-- Backward-compatible entry point. Prefer creator > generated > translated.
mp.register_script_message('fetch-sub', function(lang)
    if type(lang) ~= 'string' or not lang:match('^[%w%-]+$') or not current_url() then return end
    local entry = policy.preferred_caption(cached_captions(), lang)
    if entry then select_caption(entry) else refresh(lang) end
end)
