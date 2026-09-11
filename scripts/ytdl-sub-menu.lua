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
    ok, policy = pcall(dofile, 'scripts/modules/stream_policy.lua')
    if not ok or type(policy) ~= 'table' then
        msg.warn('Caption helper missing; using the normal uosc subtitle menu')
        local function fallback() mp.commandv('script-binding', 'uosc/subtitles') end
        mp.add_key_binding(nil, 'open', fallback)
        mp.register_script_message('open', fallback)
        mp.register_script_message('open-menu', fallback)
        return
    end
end
local epoch, revision = 0, 0
local ready = false
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
local current_temp_file = nil
local last_external_sub_id = nil
local current_sub_url = nil

local function cleanup_temp_file()
    if current_temp_file and utils.file_info(current_temp_file) then
        os.remove(current_temp_file)
        current_temp_file = nil
    end
end

local function reset()
    epoch, revision = epoch + 1, revision + 1
    ready = false
    captions, choices = nil, {}
    cancel_job()
    cleanup_temp_file()
    last_external_sub_id = nil
    current_sub_url = nil
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
    if not captions then
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
local function ensure_vtt_url(raw_url)
    if type(raw_url) ~= 'string' then return raw_url end
    if raw_url:match('%.vtt$') or raw_url:find('%.vtt%?') then return raw_url end
    local sub_url = raw_url:gsub('fmt=[%a%d]+', 'fmt=vtt')
    if not sub_url:find('fmt=vtt') then
        sub_url = sub_url .. (sub_url:find('%?') and '&' or '?') .. 'fmt=vtt'
    end
    return sub_url
end

local temp_counter = 0
local function get_temp_sub_path(suffix)
    temp_counter = temp_counter + 1
    local temp_dir = os.getenv('TEMP') or os.getenv('TMP') or os.getenv('TMPDIR') or '/tmp'
    temp_dir = temp_dir:gsub('\\', '/')
    local pid = tostring(mp.get_property_native('pid') or 0)
    return string.format('%s/mpv_sub_%s_%d_%d%s.vtt', temp_dir, pid, os.time(), temp_counter, suffix or '')
end

local function find_curl()
    local sys_curl = 'C:\\Windows\\System32\\curl.exe'
    if utils.file_info(sys_curl) then return sys_curl end
    return 'curl'
end

local function is_valid_sub_file(path)
    if not path then return false end
    local f = io.open(path, 'r')
    if not f then return true end
    local chunk = f:read(512) or ''
    f:close()
    if chunk:find('<html', 1, true) or chunk:find('<HEAD', 1, true) or chunk:find('<head', 1, true) or chunk:find('<?xml', 1, true) then
        return false
    end
    return true
end

local function find_cookies_file()
    local cf = mp.get_property('cookies-file')
    if cf and cf ~= '' and utils.file_info(cf) then return cf end
    local mpv_home = mp.command_native and mp.command_native({'expand-path', '~~/'})
    if mpv_home then
        for _, name in ipairs({'cookies.txt', 'youtube_cookies.txt'}) do
            local candidate = (mpv_home .. '/' .. name):gsub('\\', '/')
            local info = utils.file_info(candidate)
            if info and info.is_file then return candidate end
        end
    end
    return nil
end

local function find_python()
    if package.config:sub(1,1) ~= '\\' then
        for _, bin in ipairs({'/usr/bin/python3', '/usr/local/bin/python3', 'python3', 'python'}) do
            if utils.file_info(bin) then return bin end
        end
        return 'python3'
    end
    local localappdata = (os.getenv('LOCALAPPDATA') or ''):gsub('\\', '/')
    local programfiles = (os.getenv('ProgramFiles') or ''):gsub('\\', '/')
    local candidates = {
        localappdata ~= '' and (localappdata .. '/Programs/Python/Python311/python.exe'),
        localappdata ~= '' and (localappdata .. '/Programs/Python/Python312/python.exe'),
        localappdata ~= '' and (localappdata .. '/Programs/Python/Python313/python.exe'),
        localappdata ~= '' and (localappdata .. '/Programs/Python/Python310/python.exe'),
        programfiles ~= '' and (programfiles .. '/Python311/python.exe'),
        programfiles ~= '' and (programfiles .. '/Python312/python.exe'),
        'C:/Python311/python.exe',
        'C:/Python312/python.exe',
        'python',
        'python3',
    }
    for _, c in ipairs(candidates) do
        if c and utils.file_info(c) then return c end
    end
    return 'python'
end

local function find_translator()
    local appdata = (os.getenv('APPDATA') or ''):gsub('\\', '/')
    local userprofile = (os.getenv('USERPROFILE') or ''):gsub('\\', '/')
    local candidates = {
        mp.find_config_file and mp.find_config_file('tools/vtt_translate.py'),
        appdata ~= '' and (appdata .. '/mpv/tools/vtt_translate.py'),
        userprofile ~= '' and (userprofile .. '/Desktop/mpv-config/tools/vtt_translate.py'),
        'tools/vtt_translate.py',
    }
    for _, path in ipairs(candidates) do
        if path and utils.file_info(path) then return path end
    end
    return nil
end

local function find_base_caption()
    local all = cached_captions()
    for _, c in ipairs(all) do
        if (c.kind == 'manual' or c.kind == 'automatic') and (c.lang == 'en' or c.lang:match('^en%-')) then
            return c
        end
    end
    for _, c in ipairs(all) do
        if c.kind == 'manual' or c.kind == 'automatic' then
            return c
        end
    end
    return nil
end

local function mount_caption(path, title, lang, entry_url)
    local prev_temp = current_temp_file
    current_temp_file = path
    current_sub_url = entry_url
    if prev_temp and prev_temp ~= path and utils.file_info(prev_temp) then
        os.remove(prev_temp)
    end

    local sid_observer, timeout_timer
    local old_sub_id = last_external_sub_id
    sid_observer = function(name, new_sid)
        local sid_num = tonumber(new_sid)
        if sid_num and sid_num ~= old_sub_id then
            if timeout_timer then timeout_timer:kill(); timeout_timer = nil end
            if old_sub_id then
                mp.commandv('sub-remove', tostring(old_sub_id))
            end
            last_external_sub_id = sid_num
            mp.unobserve_property(sid_observer)
        end
    end
    timeout_timer = mp.add_timeout(2.5, function()
        if sid_observer then
            mp.unobserve_property(sid_observer)
            sid_observer = nil
        end
    end)
    mp.observe_property('sid', 'native', sid_observer)

    mp.commandv('sub-add', path, 'select', title, lang)
    mp.set_property_bool('sub-visibility', true)
    mp.osd_message('Captions on: ' .. title, 3)
end

select_caption = function(entry)
    if not current_url() or not entry or not policy.http_url(entry.url) then return end
    for _, track in ipairs(mp.get_property_native('track-list', {})) do
        if track.type == 'sub' and (track['external-filename'] == entry.url or (current_sub_url == entry.url and current_temp_file and track['external-filename'] == current_temp_file)) then
            select_loaded(track.id, epoch)
            return
        end
    end
    if job and job.label == entry.url then return end
    local title = entry.name .. ' - ' .. kind_names[entry.kind]

    local target_url = ensure_vtt_url(entry.url)
    local temp_path = get_temp_sub_path('_out')
    local cookie_file = find_cookies_file()
    local user_agent = mp.get_property('file-local-options/user-agent') or 'Mozilla/5.0'

    local base = (entry.kind == 'translated') and find_base_caption()
    local translator = base and find_translator()

    -- Fast-path for translated tracks without cookies:
    -- YouTube timedtext?tlang=XX blocks unauthenticated curl with HTTP 429.
    -- Directly download the base (English/source) transcript and translate locally in ~0.7s.
    if entry.kind == 'translated' and not cookie_file and base and translator then
        mp.osd_message('Translating to ' .. entry.name .. '...', 3)
        local base_url = ensure_vtt_url(base.url)
        local base_temp = get_temp_sub_path('_base')
        local base_curl_args = {
            find_curl(), '-s', '-f', '-L', '--compressed',
            '--max-time', '15',
            '-H', 'User-Agent: ' .. user_agent,
            base_url, '-o', base_temp,
        }
        start_async({
            name = 'subprocess',
            playback_only = false,
            capture_stdout = false,
            capture_stderr = true,
            args = base_curl_args,
        }, base.url, function(base_ok, base_res)
            if not base_ok or (type(base_res) == 'table' and base_res.status ~= 0) or not is_valid_sub_file(base_temp) then
                if utils.file_info(base_temp) then os.remove(base_temp) end
                mp.osd_message('Could not load base captions. Refresh the list and retry.', 4)
                return
            end

            local py_cmd = {find_python(), translator, '--input', base_temp, '--output', temp_path, '--target', entry.lang, '--source', base.lang or 'en'}
            start_async({
                name = 'subprocess',
                playback_only = false,
                capture_stdout = false,
                capture_stderr = true,
                args = py_cmd,
            }, 'translate:' .. entry.lang, function(trans_ok, trans_res)
                if utils.file_info(base_temp) then os.remove(base_temp) end
                if not trans_ok or (type(trans_res) == 'table' and trans_res.status ~= 0) or not is_valid_sub_file(temp_path) then
                    if utils.file_info(temp_path) then os.remove(temp_path) end
                    mp.osd_message('Translation failed. Refresh and retry.', 4)
                    return
                end
                mount_caption(temp_path, title, entry.lang, entry.url)
            end)
        end)
        return
    end

    mp.osd_message('Loading ' .. title .. '...', 3)

    local raw_temp = get_temp_sub_path('_raw')
    local args = {
        find_curl(),
        '-s', '-f', '-L', '--compressed',
        '--max-time', '15',
        '-H', 'User-Agent: ' .. user_agent,
    }
    if cookie_file then
        table.insert(args, '--cookie')
        table.insert(args, cookie_file)
    end
    table.insert(args, target_url)
    table.insert(args, '-o')
    table.insert(args, raw_temp)

    start_async({
        name = 'subprocess',
        playback_only = false,
        capture_stdout = false,
        capture_stderr = true,
        args = args,
    }, entry.url, function(success, result)
        if not success or (type(result) == 'table' and result.status ~= 0) or not is_valid_sub_file(raw_temp) then
            if utils.file_info(raw_temp) then os.remove(raw_temp) end

            if base and translator then
                mp.osd_message('Translating to ' .. entry.name .. '...', 3)
                local base_url = ensure_vtt_url(base.url)
                local base_temp = get_temp_sub_path('_base')
                local base_curl_args = {
                    find_curl(), '-s', '-f', '-L', '--compressed',
                    '--max-time', '15',
                    '-H', 'User-Agent: ' .. user_agent,
                    base_url, '-o', base_temp,
                }
                start_async({
                    name = 'subprocess',
                    playback_only = false,
                    capture_stdout = false,
                    capture_stderr = true,
                    args = base_curl_args,
                }, base.url, function(base_ok, base_res)
                    if not base_ok or (type(base_res) == 'table' and base_res.status ~= 0) or not is_valid_sub_file(base_temp) then
                        if utils.file_info(base_temp) then os.remove(base_temp) end
                        mp.osd_message('Could not load base captions. Refresh the list and retry.', 4)
                        return
                    end

                    local py_cmd = {find_python(), translator, '--input', base_temp, '--output', temp_path, '--target', entry.lang, '--source', base.lang or 'en'}
                    start_async({
                        name = 'subprocess',
                        playback_only = false,
                        capture_stdout = false,
                        capture_stderr = true,
                        args = py_cmd,
                    }, 'translate:' .. entry.lang, function(trans_ok, trans_res)
                        if utils.file_info(base_temp) then os.remove(base_temp) end
                        if not trans_ok or (type(trans_res) == 'table' and trans_res.status ~= 0) or not is_valid_sub_file(temp_path) then
                            if utils.file_info(temp_path) then os.remove(temp_path) end
                            mp.osd_message('Translation failed. Refresh and retry.', 4)
                            return
                        end
                        mount_caption(temp_path, title, entry.lang, entry.url)
                    end)
                end)
                return
            end

            mp.osd_message('Could not load captions. Refresh the list and retry.', 4)
            msg.warn('Caption download via curl failed: ' .. (target_url or ''))
            return
        end

        -- Clean raw VTT (strip align:start position:100% and karaoke tags)
        local py_translator = find_translator()
        if py_translator then
            local clean_path = get_temp_sub_path('_clean')
            local py_clean = {find_python(), py_translator, '--clean-only', '--input', raw_temp, '--output', clean_path, '--target', entry.lang}
            start_async({
                name = 'subprocess',
                playback_only = false,
                capture_stdout = false,
                capture_stderr = true,
                args = py_clean,
            }, 'clean:' .. entry.lang, function(clean_ok, clean_res)
                if clean_ok and (type(clean_res) ~= 'table' or clean_res.status == 0) and is_valid_sub_file(clean_path) then
                    if utils.file_info(raw_temp) then os.remove(raw_temp) end
                    mount_caption(clean_path, title, entry.lang, entry.url)
                else
                    if utils.file_info(clean_path) then os.remove(clean_path) end
                    mount_caption(raw_temp, title, entry.lang, entry.url)
                end
            end)
            return
        end

        mount_caption(raw_temp, title, entry.lang, entry.url)
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
    local more_translated = {}
    for i, entry in ipairs(cached_captions()) do
        local token = epoch .. ':' .. revision .. ':' .. i
        choices[token] = entry
        local item = {title = entry.name, icon = entry.kind == 'translated' and 'translate' or 'subtitles',
            hint = entry.lang:upper() .. ' - ' .. kind_names[entry.kind], value = message('select-caption', token)}
        if entry.kind == 'translated' and entry.is_primary == false then
            more_translated[#more_translated + 1] = item
        else
            local group = groups[entry.kind]
            if group then group[#group + 1] = item end
        end
    end
    for _, kind in ipairs({'manual', 'automatic', 'translated'}) do
        local group = groups[kind]
        if group and #group > 0 then
            local submenu_items = {}
            for _, itm in ipairs(group) do submenu_items[#submenu_items + 1] = itm end
            if kind == 'translated' and #more_translated > 0 then
                submenu_items[#submenu_items + 1] = {
                    title = 'More languages...', hint = tostring(#more_translated),
                    icon = 'translate', items = more_translated,
                }
            end
            items[#items + 1] = {title = kind_names[kind], hint = tostring(#group),
                icon = kind == 'translated' and 'translate' or 'subtitles', items = submenu_items}
        elseif kind == 'translated' and #more_translated > 0 then
            items[#items + 1] = {title = kind_names[kind], hint = tostring(#more_translated),
                icon = 'translate', items = more_translated}
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
    -- Keep a JSON codec's secondary status/error return out of command arguments.
    local menu_json = utils.format_json({
        type = 'ytdl_sub_menu', title = 'Subtitles / YouTube captions', items = items})
    mp.commandv('script-message-to', 'uosc', 'open-menu', menu_json)
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
