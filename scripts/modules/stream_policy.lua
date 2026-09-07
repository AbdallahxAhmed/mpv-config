-- Pure metadata policy: no mpv calls, processes, downloads, timers or disk writes.
local M = {}
local function positive(value)
    local n = tonumber(value)
    return n and n > 0 and n < math.huge and n or nil
end
function M.http_url(value)
    if type(value) ~= 'string' or value:find('[%c%s]') then return nil end
    local scheme, host = value:match('^(%a+)://([^/?#]+)')
    if not scheme or not host or host:find('@', 1, true) then return nil end
    scheme = scheme:lower()
    if scheme ~= 'https' and scheme ~= 'http' then return nil end
    return value
end
function M.youtube_url(value)
    if type(value) ~= 'string' then return nil end
    value = value:gsub('^ytdl://', '', 1)
    if not M.http_url(value) then return nil end
    local host = value:match('^%a+://([^/?#]+)'):lower():gsub(':%d+$', '')
    if host == 'youtu.be' or host == 'youtube.com' or host:match('^[%w%.%-]+%.youtube%.com$')
       or host == 'youtube-nocookie.com' or host:match('^[%w%.%-]+%.youtube%-nocookie%.com$') then
        return value
    end
    return nil
end
local aliases = {ara = 'ar', eng = 'en', jpn = 'ja', jap = 'ja'}
function M.language(value)
    if type(value) ~= 'string' then return '' end
    local lang = value:lower():gsub('_', '-'):gsub('%-orig$', '')
    local base, tail = lang:match('^([a-z]+)(.*)$')
    return base and ((aliases[base] or base) .. tail) or lang
end
function M.language_rank(lang, preferences)
    lang = M.language(lang)
    local base = lang:match('^[^-]+')
    if type(preferences) == 'string' then
        local list = {}
        for value in preferences:gmatch('[^,%s]+') do list[#list + 1] = value end
        preferences = list
    end
    for i, value in ipairs(type(preferences) == 'table' and preferences or {}) do
        value = M.language(value)
        if lang == value then return i * 2 end
        if base and base == value:match('^[^-]+') then return i * 2 + 1 end
    end
    return 10000
end
-- Preserve roles, dialects, DRC and distinct named dubs; strip only known
-- rendition-quality words, not arbitrary text describing the actual audio.
local function audio_group(track)
    local lang = M.language(track.language or track.lang)
    if lang == '' or lang == 'und' then return nil end
    local note = tostring(track.format_note or ''):lower()
    for _, quality in ipairs({'ultralow', 'low', 'medium', 'high', 'tiny'}) do
        note = note:gsub('%f[%a]' .. quality .. '%f[%A]', '')
    end
    note = note:gsub('%s+', ' '):gsub('^[%s,]+', ''):gsub('[%s,]+$', '')
    return table.concat({lang, tostring(track.audio_track_id or ''),
        tostring(track.language_preference or ''), note}, '\0')
end
local function audio_only(track)
    return type(track) == 'table' and track.vcodec == 'none'
        and type(track.acodec) == 'string' and track.acodec ~= 'none'
        and not track.has_drm and M.http_url(track.url) ~= nil
end
function M.audio_bitrate(track, duration)
    if not audio_only(track) then return nil end
    local rate = positive(track.abr) or positive(track.tbr)
    local size = positive(track.filesize) or positive(track.filesize_approx)
    if not rate and size and positive(duration) then rate = size * 8 / duration / 1000 end
    return rate
end
-- Two linear passes. All video/muxed formats survive untouched. Live streams,
-- non-YouTube extractors and ambiguous language/bitrate metadata are not pruned.
-- remap preserves the default audio LANGUAGE when a lower-bitrate default loses.
function M.best_audio_formats(json, formats)
    local remap = {}
    if type(json) ~= 'table' or type(formats) ~= 'table' or json.is_live
       or not (json.extractor == 'youtube' or json.extractor_key == 'Youtube') then
        return formats, remap
    end
    local has_video = false
    for _, f in ipairs(formats) do
        if type(f) == 'table' and f.vcodec and f.vcodec ~= 'none'
           and f.acodec == 'none' then has_video = true; break end
    end
    if not has_video then return formats, remap end
    local winners, groups = {}, {}
    for i, f in ipairs(formats) do
        local rate = M.audio_bitrate(f, json.duration)
        local key = rate and audio_group(f)
        if key then
            groups[i] = key
            -- yt-dlp sorts worst to best; preserve its preference on equal rates.
            if not winners[key] or rate >= winners[key].rate then
                winners[key] = {index = i, rate = rate, track = f}
            end
        end
    end
    local filtered = {}
    for i, f in ipairs(formats) do
        local best = groups[i] and winners[groups[i]]
        if not best or best.index == i then filtered[#filtered + 1] = f end
        if best and f.format_id and best.track.format_id then remap[f.format_id] = best.track.format_id end
    end
    return filtered, remap
end
function M.lazy_subtitles(url, raw_options)
    if not M.youtube_url(url) then return false end
    for _, key in ipairs({'sub-lang', 'sub-langs', 'srt-lang', 'all-subs',
        'write-subs', 'write-srt', 'write-auto-subs', 'write-automatic-subs',
        'no-write-subs', 'no-write-auto-subs'}) do
        if (raw_options or {})[key] ~= nil then return false end
    end
    return true
end
local subtitle_formats = {vtt = 1, srt = 2, ass = 3, ttml = 4}
function M.captions(json, preferences)
    local result = {}
    if type(json) ~= 'table' then return result end
    for _, group in ipairs({'subtitles', 'automatic_captions'}) do
        for lang, entries in pairs(type(json[group]) == 'table' and json[group] or {}) do
            local best, score
            if type(lang) == 'string' and type(entries) == 'table' and lang ~= 'live_chat' then
                for _, entry in ipairs(entries) do
                    if type(entry) == 'table' and subtitle_formats[entry.ext] and M.http_url(entry.url) then
                        local candidate = subtitle_formats[entry.ext]
                        if not score or candidate < score then best, score = entry, candidate end
                    end
                end
            end
            if best then
                local translated = group == 'automatic_captions' and best.url:find('[?&]tlang=') ~= nil
                local kind = group == 'subtitles' and 'manual' or (translated and 'translated' or 'automatic')
                result[#result + 1] = {url = best.url, lang = M.language(lang), key = lang,
                    name = type(best.name) == 'string' and best.name or lang:upper(),
                    kind = kind, ext = best.ext, rank = M.language_rank(lang, preferences)}
            end
        end
    end
    table.sort(result, function(a, b)
        if a.rank ~= b.rank then return a.rank < b.rank end
        if a.lang ~= b.lang then return a.lang < b.lang end
        if a.kind ~= b.kind then return a.kind < b.kind end
        return a.key < b.key
    end)
    return result
end
function M.preferred_caption(captions, lang)
    local best, score
    local kinds = {manual = 0, automatic = 1, translated = 2}
    for _, entry in ipairs(captions) do
        local rank = M.language_rank(entry.lang, {lang})
        local candidate = rank * 10 + kinds[entry.kind]
        if rank < 10000 and (not score or candidate < score) then best, score = entry, candidate end
    end
    return best
end
return M
