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

-- ── Default streaming quality (script-opts/stream_quality.conf) ──────
-- The saved default is the single source of truth for new streams; the
-- in-memory cached copy refreshes on every menu open / save / reset so
-- hand-edited files need no restart.
local quality_conf_name = 'script-opts/stream_quality.conf'
local quality_default

local function quality_conf_path()
    local found = mp.find_config_file and mp.find_config_file(quality_conf_name)
    if found then return found end
    local config_dir = nil
    local ok_dir, dir = pcall(mp.get_property, "config-dir")
    if ok_dir and dir and dir ~= '' then config_dir = dir end
    if config_dir and config_dir ~= '' then
        local sep = config_dir:sub(-1)
        if sep ~= '/' and sep ~= '\\' then config_dir = config_dir .. '/' end
        return config_dir .. quality_conf_name
    end
    if mp.find_config_file then
        local probe = mp.find_config_file('mpv.conf')
        if probe then
            local base = probe:match('^(.*[/\\])[^/\\]+$')
            if base then return base .. quality_conf_name end
        end
    end
    return nil
end

local function read_default_quality()
    local path = quality_conf_path()
    if not path then return nil end
    local f = io.open(path, 'r')
    if not f then return nil end
    local q
    for line in f:lines() do
        local v = line:match('^%s*default_quality%s*=%s*(%-?%d+)%s*$')
        if v then q = tonumber(v) end
    end
    f:close()
    return q
end

local function persist_default_quality(q)
    local path = quality_conf_path()
    if not path or not io.open then
        msg.warn('Cannot save stream default: no writable config dir')
        mp.osd_message('Default quality: could not save (no config dir)', 2)
        return false
    end
    local lines = {}
    local f = io.open(path, 'r')
    if f then
        for line in f:lines() do
            if not line:match('^%s*default_quality%s*=') then lines[#lines + 1] = line end
        end
        f:close()
    else
        lines[#lines + 1] = '# Default streaming quality ceiling (height in pixels; 0 = no cap).'
    end
    lines[#lines + 1] = 'default_quality=' .. tostring(q)
    local out = io.open(path, 'w')
    if not out then
        msg.warn('Cannot save stream default: write failed for ' .. tostring(path))
        mp.osd_message('Default quality: could not save', 2)
        return false
    end
    out:write(table.concat(lines, '\n'))
    out:write('\n')
    out:close()
    quality_default = q
    return true
end

quality_default = read_default_quality()

local function default_quality_label()
    if policy and policy.quality_label then
        local l = policy.quality_label(nil, quality_default and quality_default > 0 and quality_default or nil)
        if l then return l end
    end
    if not quality_default or quality_default <= 0 then return 'any resolution' end
    if quality_default >= 2160 then return '4K (' .. quality_default .. 'p)' end
    return quality_default .. 'p'
end

-- Restore the position once the new load is up (shared by the regular
-- reload and the fast switch below).
local function restore_position(duration, time_pos)
    if duration and duration > 0 and time_pos then
        local function on_reload()
            mp.unregister_event(on_reload)
            pcall(mp.commandv, 'seek', time_pos, 'absolute')
        end
        mp.register_event('file-loaded', on_reload)
    end
end

-- Replay the current entry and restore the position once the new load is up.
-- This re-runs the whole yt-dlp extraction (~3 s round-trip measured on the
-- shipping binary), so the fast switch below is preferred whenever it can.
local function reload_stream()
    local duration = mp.get_property_native('duration')
    local time_pos = mp.get_property('time-pos')
    mp.command('playlist-play-index current')
    restore_position(duration, time_pos)
end

-- ─── Fast quality switch ─────────────────────────────────────────────
-- A resolution switch normally replays the playlist entry, which makes
-- yt-dlp re-extract the whole video even though the toolbar already holds
-- the signed stream URLs from the last extraction. This path reuses them:
-- load the chosen video URL directly with the best audio URL as a
-- secondary track — zero yt-dlp round-trips, position restored as usual.

local function safe_media_url(u)
    return type(u) == 'string'
        and (u:find('^https://') == 1 or u:find('^http://') == 1)
        and u:find('127%.0%.0%.1') == nil and u:find('localhost') == nil
end

local function cached_stream_json()
    local res_data = mp.get_property_native('user-data/mpv/ytdl/json-subprocess-result')
    if type(res_data) ~= 'table' or res_data.status ~= 0
        or type(res_data.stdout) ~= 'string' then return nil end
    local parsed = utils.parse_json(res_data.stdout)
    if type(parsed) ~= 'table' or type(parsed.formats) ~= 'table' then return nil end
    return parsed
end

-- Pick one video row for the switch. is_cap=true matches the streaming
-- default semantics: best row at or below the ceiling, ordered by height,
-- then fps, then bitrate — yt-dlp's own selection weighs height first too.
-- HLS/fragmented rows load through the regular reload path instead.
local function pick_video_format(formats, target_h, is_cap)
    local best
    for _, f in ipairs(formats) do
        if type(f) == 'table'
            and f.vcodec and f.vcodec ~= 'none'
            and f.height and f.height > 0
            and not f.fragments
            and (f.protocol == 'https' or f.protocol == 'http')
            and safe_media_url(f.url)
        then
            local matches
            if is_cap then
                matches = not target_h or f.height <= target_h
            else
                matches = math.abs(f.height - target_h) <= 15
            end
            if matches then
                local better = not best
                    or f.height > best.height
                    or (f.height == best.height
                        and ((f.fps or 0) > (best.fps or 0)
                            or (f.fps == best.fps and (f.tbr or 0) > (best.tbr or 0))))
                if better then best = f end
            end
        end
    end
    return best
end

local function pick_audio_format(formats)
    local best
    for _, f in ipairs(formats) do
        if type(f) == 'table'
            and f.acodec and f.acodec ~= 'none'
            and (not f.vcodec or f.vcodec == 'none')
            and not f.fragments
            and (f.protocol == 'https' or f.protocol == 'http')
            and safe_media_url(f.url)
        then
            local rate = f.abr or f.tbr
            local best_rate = best and (best.abr or best.tbr)
            if not best or (rate and (not best_rate or rate > best_rate)) then
                best = f
            end
        end
    end
    return best
end

-- Reuse the same HTTP presentation the hook applies per load.
local function apply_stream_headers(opts, headers)
    if type(headers) ~= 'table' then return end
    local useragent = headers['User-Agent']
    if useragent then opts['user-agent'] = useragent end
    local extra = {}
    for _, name in ipairs({'Cookie', 'Referer', 'X-Forwarded-For'}) do
        if headers[name] then extra[#extra + 1] = name .. ': ' .. headers[name] end
    end
    if #extra > 0 then
        -- List options can't go through the per-file options table, so they
        -- ride the file-local property exactly like the hook sets them.
        mp.set_property_native('file-local-options/http-header-fields', extra)
    end
end

local function fallback_format(target_h)
    return policy and policy.stream_default_format and policy.stream_default_format(target_h)
        or 'bestvideo[height<=?' .. target_h .. ']+bestaudio/best[height<=?' .. target_h .. ']'
end

local pending_fast = nil

-- After a fast switch the replaced file's end ran the hook's cleanup, which
-- drops the parsed extraction. Put the snapshots back: the URL pair that just
-- loaded came from exactly that extraction, so it is still current evidence.
-- Later switches stay on the fast path, and the quality menu keeps listing
-- the stream's real rows instead of falling back to the guess-list.
-- Everything goes through the native getter/setter: mpv prints a
-- user-data string in its quoted form, so a plain get/set round-trip would
-- store "https://..." (with the quotes) and turn is-youtube's boolean into
-- the string "true" (get_property_bool on that returns nil, not false).
local function fast_switch_restore(attempt)
    if attempt.json_snapshot ~= nil then
        mp.set_property_native('user-data/mpv/ytdl/json-subprocess-result',
            attempt.json_snapshot)
    end
    if attempt.source_snapshot ~= nil then
        mp.set_property_native('user-data/mpv/ytdl/source-url',
            attempt.source_snapshot)
    end
    if attempt.youtube_snapshot ~= nil then
        mp.set_property_native('user-data/mpv/ytdl/is-youtube',
            attempt.youtube_snapshot)
    end
end

-- The fast load is treated as settled only when mpv really shows the new
-- stream. If it never does (signed URL expired/rejected), the cached
-- extraction is stale: drop it and run the full pipeline once, which
-- re-extracts and re-signs everything.
local function arm_fast_watch(attempt, target_h, is_cap)
    local ok_timer, timer = pcall(mp.add_timeout, 15, function()
        if pending_fast ~= attempt then return end
        pending_fast = nil
        -- Drop EVERY piece of the stale extraction, not just the parsed
        -- JSON: a half-cleared cache leaves the quality menu claiming the
        -- stream offers nothing (and the download button pointing at a
        -- video that is no longer loaded).
        pcall(mp.del_property, 'user-data/mpv/ytdl/json-subprocess-result')
        pcall(mp.del_property, 'user-data/mpv/ytdl/source-url')
        pcall(mp.del_property, 'user-data/mpv/ytdl/is-youtube')
        pcall(mp.del_property, 'user-data/mpv/ytdl/fast-url')
        pcall(mp.del_property, 'user-data/mpv/ytdl/fast-source-url')
        pcall(mp.del_property, 'user-data/mpv/ytdl/fast-headers')
        mp.osd_message('Quality switch failed — reloading a fresh stream', 2)
        msg.warn('fast switch stalled; dropping stale extraction cache')
        if is_cap then
            mp.set_property('ytdl-format', '')
        else
            mp.set_property('ytdl-format', fallback_format(target_h))
        end
        reload_stream()
    end)
    if ok_timer then attempt.timer = timer end
    local function on_loaded()
        local path = mp.get_property('path')
        if pending_fast ~= attempt then
            mp.unregister_event(on_loaded)
            return
        end
        if path == attempt.url or path == attempt.video_url then
            mp.unregister_event(on_loaded)
            pending_fast = nil
            if attempt.timer then pcall(attempt.timer.kill, attempt.timer) end
            pcall(mp.del_property, 'user-data/mpv/ytdl/fast-headers')
            fast_switch_restore(attempt)
        end
    end
    mp.register_event('file-loaded', on_loaded)
end

-- Returns true when the switch was performed without re-extraction.
local function switch_quality(target_h, is_cap)
    local parsed = cached_stream_json()
    if not parsed then return false end
    -- The hook's end-file cleanup wipes the extraction props when the
    -- replaced load ends; this fast load came from exactly that extraction,
    -- so the toolbar repairs them afterwards (see fast_switch_restore).
    -- get_property_native, not get_property: mpv prints a user-data
    -- STRING in its quoted form ("https://..."), so the raw URL would
    -- never match the hook's comparison, and is-youtube's boolean would
    -- come back as the string "true".
    local json_snapshot = mp.get_property_native('user-data/mpv/ytdl/json-subprocess-result')
    local source_snapshot = mp.get_property_native('user-data/mpv/ytdl/source-url')
    local youtube_snapshot = mp.get_property_native('user-data/mpv/ytdl/is-youtube')
    local video = pick_video_format(parsed.formats, target_h, is_cap)
    if not video then return false end
    local audio = nil
    if not video.acodec or video.acodec == 'none' then
        audio = pick_audio_format(parsed.formats)
        if not audio then return false end
    end

    restore_position(mp.get_property_native('duration'), mp.get_property('time-pos'))

    local opts = {}
    apply_stream_headers(opts, video.http_headers or parsed.http_headers)
    if audio then opts['audio-file'] = audio.url end

    -- Preserve the canonical source URL in mpv's playlist instead of
    -- overwriting it with a transient signed stream URL.
    local load_url = source_snapshot or video.url
    mp.set_property('user-data/mpv/ytdl/fast-url', video.url)
    if source_snapshot then
        mp.set_property('user-data/mpv/ytdl/fast-source-url', source_snapshot)
    end
    local headers = video.http_headers or parsed.http_headers
    if headers then
        mp.set_property_native('user-data/mpv/ytdl/fast-headers', headers)
    end
    local args = {'loadfile', load_url, 'replace', -1}
    -- mpv REJECTS an empty per-file options table ("argument options has
    -- incompatible type"), so the table is only passed when it carries
    -- something. An empty one would fail the whole load silently.
    if next(opts) ~= nil then args[5] = opts end
    -- mp.command_native reports a rejected command as (nil, err) — it does
    -- NOT raise, so a pcall around it would always look successful: the
    -- failure was swallowed, the fast markers stayed behind (a later load
    -- of the canonical URL would be hijacked into the stale stream) and
    -- the UI sat there until the heal watcher fired.
    local res, err = mp.command_native(args)
    if not res then
        pcall(mp.del_property, 'user-data/mpv/ytdl/fast-url')
        pcall(mp.del_property, 'user-data/mpv/ytdl/fast-source-url')
        pcall(mp.del_property, 'user-data/mpv/ytdl/fast-headers')
        msg.warn('fast switch failed to load: ' .. tostring(err))
        return false
    end

    if pending_fast and pending_fast.timer then
        pcall(pending_fast.timer.kill, pending_fast.timer)
    end
    local attempt = {
        url = load_url,
        video_url = video.url,
        json_snapshot = json_snapshot,
        source_snapshot = source_snapshot,
        youtube_snapshot = youtube_snapshot,
    }
    pending_fast = attempt
    arm_fast_watch(attempt, target_h, is_cap)
    return true
end

-- Stats-for-nerds labels the window size 'Display: Resolution', so a 720p
-- source fullscreened on a 1080p monitor reads as if the quality never
-- changed. Spell the rescale out whenever the playing surface differs.
local function display_note(target_h)
    if not target_h or target_h <= 0 then return '' end
    local display_w = mp.get_property_number('osd-width')
    local display_h = mp.get_property_number('osd-height')
    if not display_h or display_h <= 0 or math.abs(display_h - target_h) <= 15 then return '' end
    local size = display_w and display_w > 0
        and string.format('%dx%d', display_w, display_h)
        or (display_h .. 'p')
    return ' (' .. (display_h > target_h and 'upscale' or 'downscale')
        .. ': ' .. size .. ' display)'
end

local function apply_default(silent)
    -- Clear any per-session quality override; every load (including this
    -- reload) resolves the default from stream_quality.conf again. Re-read
    -- the conf first so default-off / set-default see their own write —
    -- the in-memory cache alone would lag by one action.
    mp.set_property('ytdl-format', '')
    local cached = quality_default
    quality_default = read_default_quality()
    if quality_default == nil then quality_default = cached end
    local cap = quality_default and quality_default > 0 and quality_default or nil
    if not silent then
        local label = cap and default_quality_label() or 'any resolution'
        mp.osd_message('Quality: default (' .. label .. ')' .. (cap and display_note(cap) or ''), 2)
    end
    -- Fast path reuses the signed URLs for the defaulted ceiling; the full
    -- reload remains the fallback when the cache can't serve it.
    if not switch_quality(cap, true) then
        reload_stream()
    end
end

local function save_default_quality()
    local h = mp.get_property_number('height') or mp.get_property_number('dheight')
    if not h or h <= 0 then
        mp.osd_message('Save default: play a video first', 2)
        return
    end
    if not persist_default_quality(h) then return end
    local label = policy and policy.quality_label and policy.quality_label(nil, h) or (h .. 'p')
    apply_default(true)
    mp.osd_message('Default quality saved: ' .. label .. ' — future streams start at it', 2)
end

local function clear_default_quality()
    if not persist_default_quality(0) then return end
    apply_default(true)
    mp.osd_message('Default quality: any resolution (no cap)', 2)
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
-- Canonical menu rows; the stream's real heights merge into these (rows the
-- extraction didn't offer become ceiling-only choices).
local DEFAULT_QUALITY_HEIGHTS = {2160, 1440, 1080, 720, 480, 360, 240, 144}

local function open_quality_menu()
    local current_h = mp.get_property_number('height') or mp.get_property_number('dheight') or 0
    -- Re-read the saved default so hand-edited conf files don't need a restart.
    local cached = quality_default
    quality_default = read_default_quality()
    if quality_default == nil then quality_default = cached end
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
    -- Standard rows the stream doesn't offer stay listed: picking one sets
    -- the same 'height<=?' cap, so playback falls to the best the video
    -- actually has. They're marked so real rows read as available (●) and
    -- the rest as caps you may want as default (○) — no more surprise 4K
    -- on a 1080-max video. Without an extraction (local file, non-YouTube
    -- stream, a failed switch) we know nothing about the stream, so the
    -- rows stay unmarked: claiming "not in stream" for a row we never
    -- checked would be the same lie in the other direction.
    local offered = {}
    for _, info in pairs(heights_map) do offered[info.height] = true end
    local known = formats ~= nil
    for _, h in ipairs(DEFAULT_QUALITY_HEIGHTS) do
        if not offered[h] then
            sorted_heights[#sorted_heights + 1] =
                {height = h, ceiling = true, known = known}
        end
    end
    table.sort(sorted_heights, function(a, b) return a.height > b.height end)

    local is_current_default = quality_default and quality_default > 0 or false
    local function join_hints(hints)
        if hints[1] == nil then return nil end
        if hints[2] == nil then return hints[1] end
        return hints[1] .. ' · ' .. hints[2]
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
        local hints = {}
        if is_current then hints[#hints + 1] = 'Current' end
        if is_current_default and h == quality_default then hints[#hints + 1] = 'Default' end
        if info.ceiling and info.known then hints[#hints + 1] = 'cap only · not in stream' end
        -- ● the stream really offers this height, ○ a ceiling the stream
        -- doesn't list, no marker at all when nothing is known about it.
        local marker = '●'
        if info.ceiling then marker = info.known and '○' or nil end
        items[#items + 1] = {
            title = (marker and (marker .. ' ') or '') .. label,
            hint = join_hints(hints),
            active = is_current,
            -- Two clicks to change the permanent default: open the row's
            -- submenu, pick 'Set as default'. No menu reopen, no separate
            -- save-on-playing-quality step.
            items = {
                {
                    title = 'Set as default',
                    hint = 'this + future streams',
                    value = {'script-message-to', script, 'set-default', tostring(h), label},
                },
                {
                    title = 'Just this video',
                    hint = 'temporary override',
                    value = {'script-message-to', script, 'set-quality', tostring(h), label},
                },
            },
        }
    end

    if is_current_default then
        items[#items + 1] = {
            title = 'Apply default now',
            hint = default_quality_label(),
            value = {'script-message-to', script, 'apply-default'},
        }
    end
    items[#items + 1] = {
        title = 'Default: any resolution',
        hint = 'remove the cap',
        value = {'script-message-to', script, 'default-off'},
    }

    local menu_json = utils.format_json({
        type = 'stream_quality_menu',
        title = 'Video quality',
        items = items,
    })
    if menu_json then pcall(mp.commandv, 'script-message-to', 'uosc', 'open-menu', menu_json) end
end
local function set_quality(target_h, target_label)
    local h = tonumber(target_h)
    if not h or h <= 0 then return end
    -- No-op when the playing stream is already this resolution — unless the
    -- row promises a higher frame rate than what is on screen right now.
    local parsed = cached_stream_json()
    local picked
    local is_cap = false
    if parsed and type(parsed.formats) == 'table' then
        picked = pick_video_format(parsed.formats, h, is_cap)
        if not picked then
            -- The requested height is not in the stream as an exact row (a
            -- ceiling row, or a height the extraction simply lacks): cap it
            -- instead of failing the switch outright, so playback falls to
            -- the best the video actually has.
            picked = pick_video_format(parsed.formats, h, true)
            is_cap = true
        end
        local cur = mp.get_property_number('height') or mp.get_property_number('dheight') or 0
        if picked and cur > 0 and math.abs(cur - picked.height) <= 15 then
            local cur_fps = mp.get_property_number('container-fps') or 0
            if not picked.fps or cur_fps <= 0 or picked.fps <= cur_fps + 0.5 then
                local lbl = target_label or (h >= 2160 and '4K' or (h .. 'p'))
                if is_cap and policy and policy.quality_label then
                    lbl = policy.quality_label(nil, picked.height) or lbl
                end
                mp.osd_message('Quality: already ' .. lbl, 2)
                return
            end
        end
    end
    local format = policy and policy.stream_default_format and policy.stream_default_format(h)
        or 'bestvideo[height<=?' .. h .. ']+bestaudio/best[height<=?' .. h .. ']'
    mp.set_property('ytdl-format', format)
    -- Fast path: reuse the signed URLs from the last extraction; the full
    -- replay (re-extraction) remains the fallback.
    if not switch_quality(h, is_cap) then
        reload_stream()
    end
    -- A ceiling plays the best the stream really has, so report that
    -- height — not the (unreachable) ceiling the row was named after.
    local applied_h = (is_cap and picked) and picked.height or h
    local applied_label = target_label or (h >= 2160 and '4K' or (h .. 'p'))
    if is_cap and picked and policy and policy.quality_label then
        applied_label = policy.quality_label(nil, picked.height) or applied_label
    end
    mp.osd_message('Quality: ' .. applied_label .. display_note(applied_h), 2)
end

-- Set the persisted default straight from a menu row's submenu — replaces
-- the old 'play it first, then reopen the menu and save' dance. The saved
-- default also re-drives the playing stream so the change is visible at
-- once; 'Just this video' stays the session-only counterpart.
local function set_default_quality(target_h, target_label)
    local h = tonumber(target_h)
    if not h or h <= 0 then return end
    if not persist_default_quality(h) then return end
    local label = target_label or (h >= 2160 and '4K' or (h .. 'p'))
    apply_default(true)
    mp.osd_message('Default quality: ' .. label .. ' — future streams start at it', 2)
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
    if not ytdl_format or ytdl_format == '' then
        -- Stream default cap (script-opts/stream_quality.conf); no video
        -- opened yet → resolve from the saved default instead of assuming 1080p.
        ytdl_format = policy and policy.stream_default_format
            and policy.stream_default_format(quality_default) or nil
    end
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
                '--fragments', '16',
            }
            local ipc_server = mp.get_property('input-ipc-server')
            if ipc_server and ipc_server ~= '' then
                table.insert(w_args, '--ipc-pipe')
                table.insert(w_args, ipc_server)
            end
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
                    fmt = policy and policy.stream_default_format
                        and policy.stream_default_format(quality_default) or nil
                end
                if fmt then
                    table.insert(args, '-f')
                    table.insert(args, fmt)
                end
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
mp.register_script_message('set-default', set_default_quality)
mp.register_script_message('save-default', save_default_quality)
mp.register_script_message('apply-default', apply_default)
mp.register_script_message('default-off', clear_default_quality)
mp.register_script_message('start-download', function() start_download(false) end)
mp.register_script_message('download-video', function() start_download(false) end)
mp.register_script_message('download-audio', function() start_download(true) end)
mp.register_script_message('open-download-folder', open_download_folder)

-- Real-time IPC telemetry push from download_worker.py
mp.register_script_message('download-progress', function(payload_str)
    local ok, data = pcall(function() return utils.parse_json(payload_str) end)
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
end)

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
