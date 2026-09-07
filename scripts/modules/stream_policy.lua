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
local iso_3_to_2 = {
    ara = 'AR', eng = 'EN', jpn = 'JA', jap = 'JA', spa = 'ES',
    fra = 'FR', fre = 'FR', deu = 'DE', ger = 'DE',
    ita = 'IT', por = 'PT', rus = 'RU', zho = 'ZH',
    chi = 'ZH', kor = 'KO', hin = 'HI', tur = 'TR',
    ind = 'ID', pol = 'PL', ukr = 'UK', nld = 'NL',
    dut = 'NL', swe = 'SV', vie = 'VI', tha = 'TH',
    fas = 'FA', per = 'FA', heb = 'HE', ell = 'EL',
    gre = 'EL', ces = 'CS', cze = 'CS', ron = 'RO',
    rum = 'RO', hun = 'HU', dan = 'DA', fin = 'FI',
    nor = 'NO', slk = 'SK', slo = 'SK', msa = 'MS',
    may = 'MS', ben = 'BN', urd = 'UR', tam = 'TA',
    tel = 'TE', mar = 'MR',
}
local aliases = {}
for k, v in pairs(iso_3_to_2) do
    aliases[k] = v:lower()
end

local title_language_patterns = {
    {pattern = 'ara', monogram = 'AR'},
    {pattern = 'arabic', monogram = 'AR'},
    {pattern = 'eng', monogram = 'EN'},
    {pattern = 'english', monogram = 'EN'},
    {pattern = 'jap', monogram = 'JA'},
    {pattern = 'japanese', monogram = 'JA'},
    {pattern = 'spa', monogram = 'ES'},
    {pattern = 'spanish', monogram = 'ES'},
    {pattern = 'fra', monogram = 'FR'},
    {pattern = 'french', monogram = 'FR'},
    {pattern = 'ger', monogram = 'DE'},
    {pattern = 'deu', monogram = 'DE'},
    {pattern = 'german', monogram = 'DE'},
    {pattern = 'ita', monogram = 'IT'},
    {pattern = 'italian', monogram = 'IT'},
    {pattern = 'rus', monogram = 'RU'},
    {pattern = 'russian', monogram = 'RU'},
}

function M.monogram(lang_code, title)
    if type(lang_code) == 'string' and #lang_code > 0 then
        local clean = lang_code:lower():gsub('_', '-'):gsub('%-orig$', ''):match('^[a-z]+')
        if clean and clean ~= 'und' then
            if iso_3_to_2[clean] then return iso_3_to_2[clean] end
            if #clean >= 2 then return clean:sub(1, 2):upper() end
        end
    end
    if type(title) == 'string' and #title > 0 then
        local lower = title:lower()
        for _, item in ipairs(title_language_patterns) do
            if lower:find(item.pattern, 1, true) then
                return item.monogram
            end
        end
    end
    return nil
end

function M.quality_monogram(w, h)
    local width = tonumber(w) or 0
    local height = tonumber(h) or 0
    if width <= 0 and height <= 0 then return nil end
    if width >= 3840 or height >= 2160 then return '4K' end
    if width >= 1280 or height >= 720 then return 'HD' end
    return 'SD'
end

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
-- Preserve roles, dialects, DRC and distinct named dubs.
-- Deduplicate multi-language variants and prune low-priority null-codec duplicates.
local function audio_role(track)
    local note = tostring(track.format_note or ''):lower()
    if note:find('descriptive', 1, true) or note:find('desc', 1, true) then return 'descriptive' end
    if note:find('commentary', 1, true) then return 'commentary' end
    if note:find('drc', 1, true) then return 'drc' end
    if note:find('dub', 1, true) then return 'dubbed' end
    return 'main'
end
local function audio_group(track)
    local lang = M.language(track.language or track.lang)
    if lang == '' or lang == 'und' then return nil end
    local role = audio_role(track)
    return table.concat({lang, role}, '\0')
end
local function audio_only(track)
    return type(track) == 'table' and track.vcodec == 'none'
        and not track.has_drm and M.http_url(track.url) ~= nil
end
function M.audio_bitrate(track, duration)
    if not audio_only(track) then return nil end
    if not track.acodec or track.acodec == 'none' then
        return 0.1
    end
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
    local real_audio = {}
    for _, f in ipairs(formats) do
        local lang = M.language(f.language or f.lang)
        if lang ~= '' and lang ~= 'und' and f.vcodec == 'none' and f.acodec and f.acodec ~= 'none' then
            local rate = M.audio_bitrate(f, json.duration)
            if not real_audio[lang] or (rate and rate > (real_audio[lang].rate or 0)) then
                real_audio[lang] = {track = f, rate = rate or 0}
            end
        end
    end
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
        local lang = M.language(f.language or f.lang)
        local is_null_dup = (not f.acodec or f.acodec == 'none') and real_audio[lang] ~= nil
        local best = groups[i] and winners[groups[i]]
        if not is_null_dup and (not best or best.index == i) then
            filtered[#filtered + 1] = f
        end
        if is_null_dup and real_audio[lang] and f.format_id and real_audio[lang].track.format_id then
            remap[f.format_id] = real_audio[lang].track.format_id
        elseif best and f.format_id and best.track.format_id then
            remap[f.format_id] = best.track.format_id
        end
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
    local seen_auto = {}
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
                local norm_lang = M.language(lang)
                local skip = false
                if kind == 'automatic' then
                    if seen_auto[norm_lang] then
                        skip = true
                    else
                        seen_auto[norm_lang] = true
                    end
                end
                if not skip then
                    local name = type(best.name) == 'string' and best.name or lang:upper()
                    if kind == 'automatic' then
                        name = name:gsub('%s*%(Original%)', '')
                    end
                    local is_primary = (norm_lang == 'ar' or norm_lang == 'en'
                        or norm_lang:match('^ar%-') ~= nil or norm_lang:match('^en%-') ~= nil)
                    result[#result + 1] = {url = best.url, lang = norm_lang, key = lang,
                        name = name,
                        kind = kind, ext = best.ext, rank = M.language_rank(lang, preferences),
                        is_primary = is_primary}
                end
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
