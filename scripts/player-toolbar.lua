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

local last_download_key
local is_downloading = false
local download_badge = nil
local download_progress = nil
local download_tooltip = nil
local download_timer = nil

local function publish_download(force)
    local active = is_downloading
    local badge = download_badge
    local prog = download_progress
    local tooltip = download_tooltip or (active and 'Downloading in background...' or 'Download video')
    local key = tostring(active) .. ':' .. tostring(badge) .. ':' .. tostring(prog) .. ':' .. tostring(tooltip)
    if not force and last_download_key == key then return end
    last_download_key = key
    local data_tbl = {
        icon = 'file_download',
        active = active,
        badge = badge,
        tooltip = tooltip,
        command = {'script-message-to', script, 'start-download'},
    }
    if prog ~= nil then
        data_tbl.progress = prog
    end
    local data = utils.format_json(data_tbl)
    if data then pcall(mp.commandv, 'script-message-to', 'uosc', 'set-button', 'download-video', data) end
end

local function extract_clean_error(res, err)
    local raw = (res and (res.stderr or res.stdout)) or tostring(err or '')
    if type(raw) ~= 'string' or raw == '' then return 'Download failed.' end
    for line in raw:gmatch('[^\r\n]+') do
        local err_msg = line:match('ERROR:%s*(.+)')
        if err_msg then
            err_msg = err_msg:gsub('^%[.-%]%s*', '')
            if #err_msg > 65 then err_msg = err_msg:sub(1, 62) .. '...' end
            return 'Download error: ' .. err_msg
        end
    end
    return 'Download failed. Check terminal or logs.'
end

local function find_tool(name)
    local candidates = {}
    if mp.find_config_file then
        local p = mp.find_config_file('tools/' .. name)
        if p and p ~= '' then table.insert(candidates, p) end
    end
    local appdata = (os.getenv('APPDATA') or ''):gsub('\\', '/')
    if appdata ~= '' then table.insert(candidates, appdata .. '/mpv/tools/' .. name) end
    local userprofile = (os.getenv('USERPROFILE') or ''):gsub('\\', '/')
    if userprofile ~= '' then table.insert(candidates, userprofile .. '/Desktop/mpv-config/tools/' .. name) end
    table.insert(candidates, 'tools/' .. name)

    for _, path in ipairs(candidates) do
        local fi = utils and utils.file_info and utils.file_info(path)
        if fi then return path end
    end
    return nil
end

local function start_download(is_audio_only)
    if is_downloading then
        mp.osd_message('Download already in progress in background...', 3)
        return
    end

    local source_url = mp.get_property_native('user-data/mpv/ytdl/source-url')
    local path = mp.get_property('path')
    local stream_open = mp.get_property('stream-open-filename')

    local primary_url, secondary_url = nil, nil
    if policy and policy.resolve_stream_urls then
        primary_url, secondary_url = policy.resolve_stream_urls(source_url, path, stream_open)
    else
        local clean = function(raw)
            if type(raw) ~= 'string' or raw == '' then return nil end
            local s = raw:gsub('^%s+', ''):gsub('%s+$', '')
            while (#s >= 2 and (s:sub(1,1) == '"' or s:sub(1,1) == "'")) do
                s = s:sub(2, -2):gsub('^%s+', ''):gsub('%s+$', '')
            end
            if s:find('^ytdl://') then s = s:sub(8):gsub('^%s+', ''):gsub('%s+$', '') end
            if s:find('^edl://') then
                local inner = s:match('%%[0-9]+%%(https?://[^,;%s]+)') or s:match('(https?://[^,;%s]+)')
                if inner then s = inner end
            end
            if s:find('^https?://') then return s end
            return nil
        end
        primary_url = clean(source_url) or clean(path) or clean(stream_open)
    end

    if not primary_url then
        mp.osd_message('Download only works for online streams/URLs.', 3)
        return
    end

    local media_title = mp.get_property('media-title') or 'stream'

    -- Smart Cache Video Saver:
    -- If the user has already buffered/watched the video in MPV, export directly from demuxer cache!
    -- Saves instant gigabytes with 0 MB redownloaded.
    if not is_audio_only then
        local duration = mp.get_property_number('duration') or 0
        local cache_state = mp.get_property_native('demuxer-cache-state')
        local coverage = nil
        if policy and policy.analyze_cache_coverage then
            coverage = policy.analyze_cache_coverage(cache_state, duration)
        end

        if coverage and coverage.is_complete then
            local target_path = nil
            local exists_check = function(p)
                local fi = utils and utils.file_info and utils.file_info(p)
                return fi ~= nil
            end
            if policy and policy.resolve_download_target_path then
                target_path = policy.resolve_download_target_path(media_title, nil, 'mp4', exists_check)
            else
                local home = os.getenv('USERPROFILE') or os.getenv('HOME') or '.'
                local dir = home:gsub('\\', '/') .. '/Downloads'
                target_path = dir .. '/' .. media_title:gsub('[\\/:*?"<>|]', '_') .. '.mp4'
            end

            local start_t = tostring(math.max(0, math.floor(coverage.start_time or 0)))
            local end_t = tostring(math.ceil(coverage.end_time or duration))
            mp.osd_message(string.format('Saving from cache (0 MB downloaded): %s', media_title), 3)

            local ok, err = pcall(mp.commandv, 'dump-cache', start_t, end_t, target_path)
            local file_info = utils and utils.file_info and utils.file_info(target_path)
            if ok and file_info and file_info.size and file_info.size > 1024 then
                if msg and msg.info then msg.info(string.format('Successfully dumped cache to %s (%d bytes)', target_path, file_info.size)) end
                download_badge = 'SAVED'
                publish_download(true)
                mp.osd_message(string.format('Saved from cache: %s\nInstant export (0 MB downloaded!)', media_title), 5)
                if mp.add_timeout then
                    pcall(function()
                        download_timer = mp.add_timeout(4, function()
                            download_badge = nil
                            publish_download(true)
                        end)
                    end)
                end
                return
            else
                if msg and msg.warn then msg.warn('dump-cache failed or empty (' .. tostring(err) .. '), falling back to yt-dlp') end
            end
        elseif coverage and coverage.coverage_pct and coverage.coverage_pct > 0 then
            if msg and msg.info then msg.info(string.format('Partial cache coverage (%d%%), downloading complete video via yt-dlp.', coverage.coverage_pct)) end
        end
    end

    local referer = mp.get_property('referrer')
    local user_agent = mp.get_property('user-agent')
    local cookies = mp.get_property('cookies') or mp.get_property('cookies-file')
    local extra_opts = {
        referer = (referer and referer ~= '') and referer or nil,
        user_agent = (user_agent and user_agent ~= '') and user_agent or nil,
        cookies = (cookies and cookies ~= '') and cookies or nil,
    }

    local ytdl_format = mp.get_property('ytdl-format')
    local worker_script = find_tool and find_tool('download_worker.py')
    local home = os.getenv('USERPROFILE') or os.getenv('HOME') or '.'
    local default_dir = policy and policy.default_download_dir and policy.default_download_dir()
        or (home:gsub('\\', '/') .. '/Downloads')
    local template = default_dir .. '/%(title)s [%(id)s].%(ext)s'

    local make_args = function(target_url, state_file)
        if worker_script and state_file then
            local w_args = {
                'python',
                worker_script,
                '--state-file', state_file,
                '--output', template,
                '--fragments', '6',
            }
            if is_audio_only then table.insert(w_args, '--audio-only') end
            if ytdl_format and ytdl_format ~= '' then
                table.insert(w_args, '--format')
                table.insert(w_args, ytdl_format)
            end
            if extra_opts.user_agent then
                table.insert(w_args, '--user-agent')
                table.insert(w_args, extra_opts.user_agent)
            end
            if extra_opts.referer then
                table.insert(w_args, '--referer')
                table.insert(w_args, extra_opts.referer)
            end
            if extra_opts.cookies then
                table.insert(w_args, '--cookies')
                table.insert(w_args, extra_opts.cookies)
            end
            table.insert(w_args, '--url')
            table.insert(w_args, target_url)
            table.insert(w_args, target_url) -- Keep positional at end for compatibility
            return w_args
        end

        local args = nil
        if policy and policy.download_args then
            args = policy.download_args(target_url, nil, is_audio_only, ytdl_format, extra_opts)
        end
        if not args then
            args = {'yt-dlp', '--no-playlist', '--continue', '--no-overwrites', '--windows-filenames', '--no-mtime', '--concurrent-fragments', '6'}
            if is_audio_only then
                table.insert(args, '-x')
                table.insert(args, '--audio-format')
                table.insert(args, 'mp3')
                table.insert(args, '--audio-quality')
                table.insert(args, '0')
            else
                local fmt = ytdl_format
                if not fmt or fmt == '' or fmt:find('bestvideo') == nil then
                    fmt = 'bestvideo[height<=?1080]+bestaudio/best[height<=?1080]/best'
                end
                table.insert(args, '-f')
                table.insert(args, fmt)
                table.insert(args, '--merge-output-format')
                table.insert(args, 'mp4')
            end
            table.insert(args, '-o')
            table.insert(args, template)
            table.insert(args, target_url)
        end
        return args
    end

    local target_desc = is_audio_only and 'Audio (MP3)' or 'Video'
    is_downloading = true
    download_badge = 'DL'
    download_progress = 0.0
    download_tooltip = string.format('Starting %s download: %s', target_desc, media_title)
    publish_download(true)
    mp.osd_message(string.format('Starting %s download: %s', target_desc, media_title), 3)

    if download_timer then
        pcall(function() download_timer:kill() end)
        download_timer = nil
    end

    local download_poll_timer = nil
    local session_id = tostring(os.time()) .. '_' .. tostring(math.random(1000, 9999))
    local temp_dir = os.getenv('TEMP') or os.getenv('TMP') or '.'
    local state_file = temp_dir:gsub('\\', '/') .. '/mpv_dl_state_' .. session_id .. '.json'

    local function cleanup_download()
        if download_poll_timer then
            pcall(function() download_poll_timer:kill() end)
            download_poll_timer = nil
        end
        pcall(function() os.remove(state_file) end)
        pcall(function() os.remove(state_file .. '.tmp') end)
    end

    local function run_subprocess(target_url, allow_retry)
        local cmd_args = make_args(target_url, state_file)

        if worker_script and mp.add_periodic_timer then
            download_poll_timer = mp.add_periodic_timer(0.25, function()
                local content = nil
                pcall(function()
                    if utils and utils.read_file then
                        content = utils.read_file(state_file)
                    else
                        local f = io.open(state_file, 'r')
                        if f then
                            content = f:read('*a')
                            f:close()
                        end
                    end
                end)
                if content and content ~= '' then
                    local ok, data = pcall(function()
                        return utils.parse_json(content)
                    end)
                    if ok and type(data) == 'table' then
                        if data.percent_int ~= nil then
                            download_badge = tostring(data.percent_int) .. '%'
                            download_progress = (data.percent or 0) / 100
                        end
                        if data.speed and data.eta then
                            download_tooltip = string.format('Downloading: %s%% (%s • ETA %s • %s threads)',
                                tostring(data.percent_int or 0), tostring(data.speed), tostring(data.eta), tostring(data.threads or 16))
                        end
                        publish_download(true)
                    end
                end
            end)
        end

        mp.command_native_async({
            name = 'subprocess',
            playback_only = false,
            capture_stdout = true,
            capture_stderr = true,
            args = cmd_args,
        }, function(success, res, err)
            cleanup_download()
            local code = res and res.status or -1
            if success and code == 0 then
                is_downloading = false
                download_badge = 'OK'
                download_progress = 1.0
                download_tooltip = 'Download complete: Saved to Downloads folder'
                mp.osd_message(string.format('Download complete: %s\nSaved to Downloads folder', media_title), 5)
                publish_download(true)
                if mp.add_timeout then
                    pcall(function()
                        download_timer = mp.add_timeout(4, function()
                            download_badge = nil
                            download_progress = nil
                            download_tooltip = nil
                            publish_download(true)
                        end)
                    end)
                end
            elseif allow_retry and secondary_url and secondary_url ~= target_url then
                if msg and msg.info then msg.info('Primary download failed, retrying with secondary stream URL: ' .. secondary_url) end
                run_subprocess(secondary_url, false)
            else
                is_downloading = false
                download_badge = 'ERR'
                download_progress = nil
                download_tooltip = nil
                local err_line = extract_clean_error(res, err)
                if msg and msg.warn then msg.warn('Download failed: ' .. tostring(res and (res.stderr or res.stdout) or err)) end
                mp.osd_message(err_line, 5)
                publish_download(true)
                if mp.add_timeout then
                    pcall(function()
                        download_timer = mp.add_timeout(4, function()
                            download_badge = nil
                            publish_download(true)
                        end)
                    end)
                end
            end
        end)
    end

    if mp.command_native_async then
        run_subprocess(primary_url, true)
    else
        is_downloading = false
        download_badge = 'ERR'
        download_progress = nil
        download_tooltip = nil
        publish_download(true)
        mp.osd_message('Subprocess execution unavailable in this mpv build.', 3)
    end
end

local function open_download_folder()
    local dir = policy and policy.default_download_dir and policy.default_download_dir()
        or (os.getenv('USERPROFILE') or os.getenv('HOME') or '.'):gsub('\\', '/') .. '/Downloads'
    local win_dir = dir:gsub('/', '\\')
    if mp.command_native_async then
        mp.command_native_async({
            name = 'subprocess',
            playback_only = false,
            args = {'explorer', win_dir},
        })
    end
end

mp.register_script_message('open-audio-menu', open_audio_menu)
mp.register_script_message('open-quality-menu', open_quality_menu)
mp.register_script_message('set-quality', set_quality)
mp.register_script_message('start-download', function() start_download(false) end)
mp.register_script_message('download-video', function() start_download(false) end)
mp.register_script_message('download-audio', function() start_download(true) end)
mp.register_script_message('open-download-folder', open_download_folder)

-- uosc broadcasts on startup; also publish now if uosc started first.
mp.register_script_message('uosc-version', function()
    publish(nil, true)
    publish_quality(true)
    publish_audio(true)
    publish_download(true)
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
    publish_download(true)
end)
mp.register_event('end-file', function()
    if not is_downloading then
        download_badge = nil
    end
    publish_download(true)
end)
publish(nil, true)
publish_quality(true)
publish_audio(true)
publish_download(true)
