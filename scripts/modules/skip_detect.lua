-- skip_detect.lua - decide which chapters are intro / outro / preview / recap.
--
-- SmartSkip's stock matching only knows a handful of case-sensitive Lua
-- patterns ("^OP", "^Opening", "^ED" ...). Real releases are far messier:
--   * names in any case:   "opening", "Op", "ENDING", "op - Kaikai Kitan"
--   * other words:         "Intro", "Outro", "End Credits", "Theme Song",
--                          "Next Episode", "Recap", Japanese and Arabic names
--   * no names at all:     "Chapter 1".."Chapter 6", "00:00:00.000", ""
--     (very common in BD rips), where only the SHAPE of the chapter list
--     tells you where the opening and the ending are.
--
-- This module is pure Lua (no mp.* calls) so it can be unit tested
-- outside mpv. SmartSkip feeds it mpv's chapter-list and the file duration
-- and gets back one category per chapter (1-based, same as chapter-list):
--   "opening" | "ending" | "preview" | "recap" | "prologue" | nil
-- plus the reason for each decision ("name" or "length"), which SmartSkip
-- prints to the log so a wrong guess can be traced.
--
-- Two passes:
--   1. names  - normalised (lowercase, punctuation -> spaces) and matched
--               on whole words, so "Operation" is never an OP and
--               "Post-Credits Scene" / "Alternate Ending" are never skipped.
--   2. length - only for chapters with generic names, and only when no
--               chapter was named as an opening/ending: a ~1:30 chapter in
--               the first part of an episode is the opening, a ~1:30
--               chapter in the last part is the ending, and a short last
--               chapter right after the ending is the next-episode preview.

local M = {}

M.DEFAULTS = {
    heuristics = true,       -- run the length pass at all
    song_min = 75,           -- an anime OP/ED is ~89-91 s; TV-size range
    song_max = 105,
    intro_max = 120,         -- "Intro" longer than this is a cold open
    preview_max = 40,        -- next-episode previews are 10-30 s
    preview_min = 3,
    episode_min = 600,       -- length pass only for episode-sized files
    episode_max = 2700,
    op_window = 480,         -- OP must start in the first 8 min ...
    op_window_ratio = 0.4,   -- ... and in the first 40% of the file
    ed_window_ratio = 0.7,   -- ED must end in the last 30% of the file
}

local function trim(s)
    return (s:gsub('^%s+', ''):gsub('%s+$', ''))
end

-- Lowercase ASCII, punctuation to spaces, single spaces. Non-ASCII bytes
-- (Arabic, Japanese) pass through untouched.
function M.normalize(title)
    local s = tostring(title or ''):lower()
    s = s:gsub('[%-%_%.,:;|%(%)%[%]{}<>"\'!%?/\\~#%*%+=&]', ' ')
    s = s:gsub('%s+', ' ')
    return trim(s)
end

local function has_phrase(norm, phrase)
    return (' ' .. norm .. ' '):find(' ' .. phrase .. ' ', 1, true) ~= nil
end

local function has_any(norm, phrases)
    for _, p in ipairs(phrases) do
        if has_phrase(norm, p) then return true end
    end
    return false
end

local function has_substring(raw, needles)
    for _, n in ipairs(needles) do
        if raw:find(n, 1, true) then return true end
    end
    return false
end

local function tokens(norm)
    local t = {}
    for w in norm:gmatch('%S+') do t[#t + 1] = w end
    return t
end

-- A chapter name that says nothing about its content.
local GENERIC_PATTERNS = {
    '^$',
    '^chapter$', '^chapter %d+$', '^chap %d+$', '^ch %d+$', '^chapter %d+ %d+$',
    '^%d+$', '^scene %d+$', '^part %d+$',
    '^kapitel %d+$', '^chapitre %d+$', '^capitulo %d+$', '^capitolo %d+$',
    '^hoofdstuk %d+$',
}
local GENERIC_RAW_PATTERNS = {
    '^%s*%d+:%d+',                       -- "00:01:30.000" timestamps
    '^%s*cap\195\173tulo%s*%d+%s*$',     -- "Capítulo 3"
    '^%s*\216\167\217\132\217\129\216\181\217\132', -- "الفصل ..."
    '^%s*\217\129\216\181\217\132',      -- "فصل ..."
    '^%s*\227\131\129\227\131\163\227\131\151\227\130\191\227\131\188', -- "チャプター"
    '^%s*\208\147\208\187\208\176\208\178\208\176', -- "Глава"
}

function M.is_generic(title)
    if title == nil then return true end
    local raw = tostring(title)
    local norm = M.normalize(raw)
    for _, p in ipairs(GENERIC_PATTERNS) do
        if norm:match(p) then return true end
    end
    for _, p in ipairs(GENERIC_RAW_PATTERNS) do
        if raw:lower():match(p) then return true end
    end
    return false
end

-- Words that turn an "ending"/"opening"/"credits" title into real content.
local CONTENT_MARKERS = {
    'scene', 'post', 'after', 'mid', 'stinger', 'epilogue', 'alternate',
    'alternative', 'true', 'bad', 'good', 'happy', 'secret', 'real', 'extended',
}

local PREVIEW_PHRASES = {
    'preview', 'next episode', 'next ep', 'next time', 'next week',
    'yokoku', 'trailer',
}
local PREVIEW_RAW = {
    '\228\186\136\229\145\138',                 -- 予告
    '\216\167\217\132\216\173\217\132\217\130\216\169 \216\167\217\132\217\130\216\167\216\175\217\133\216\169', -- الحلقة القادمة
    '\216\167\217\132\216\173\217\132\217\130\217\135 \216\167\217\132\217\130\216\167\216\175\217\133\217\135', -- الحلقه القادمه
}

local RECAP_PHRASES = { 'recap', 'previously', 'previously on', 'last time', 'story so far' }
local RECAP_RAW = {
    '\229\137\141\229\155\158',                 -- 前回
    '\217\133\217\132\216\174\216\181',         -- ملخص
}

local OPENING_PHRASES = {
    'opening', 'opening credits', 'opening theme', 'opening song',
    'title sequence', 'main title', 'main titles', 'theme song', 'intro song',
}
local OPENING_RAW = {
    '\227\130\170\227\131\188\227\131\151\227\131\139\227\131\179\227\130\176', -- オープニング
    '\216\180\216\167\216\177\216\169 \216\167\217\132\216\168\216\175\216\167\217\138\216\169', -- شارة البداية
    '\216\170\216\170\216\177 \216\167\217\132\216\168\216\175\216\167\217\138\216\169',         -- تتر البداية
    '\216\167\217\132\217\133\217\130\216\175\217\133\216\169',                                   -- المقدمة
}

local ENDING_PHRASES = {
    'ending', 'ending credits', 'end credits', 'credits', 'closing credits',
    'outro', 'ending theme', 'ending song', 'end title', 'end titles',
    'end roll', 'staff roll', 'staff credits', 'credits start',
}
local ENDING_RAW = {
    '\227\130\168\227\131\179\227\131\135\227\130\163\227\131\179\227\130\176', -- エンディング
    '\227\130\185\227\130\191\227\131\131\227\131\149\227\131\173\227\131\188\227\131\171', -- スタッフロール
    '\216\180\216\167\216\177\216\169 \216\167\217\132\217\134\217\135\216\167\217\138\216\169', -- شارة النهاية
    '\216\170\216\170\216\177 \216\167\217\132\217\134\217\135\216\167\217\138\216\169',         -- تتر النهاية
}

local PROLOGUE_PHRASES = { 'prologue', 'avant', 'avant title', 'cold open', 'teaser' }
local PROLOGUE_RAW = { '\227\130\162\227\131\144\227\131\179' } -- アバン

-- Words allowed next to a bare "OP"/"ED" token: "OP", "OP 2", "ED Theme",
-- "NCOP TV Size". Anything else needs a separator ("ED - Song") or the
-- token at the very end ("Part B ED"), so "Ed and Al" stays content.
local SONG_FILLERS = {
    start = true, theme = true, song = true, tv = true, size = true,
    version = true, ver = true, full = true, creditless = true, clean = true,
    ['begin'] = true, begins = true,
}

local function song_token(t, prefix_set)
    for _, p in ipairs(prefix_set) do
        if t == p or t:match('^' .. p .. '%d+$') then return true end
    end
    return false
end

local OP_TOKENS = { 'op', 'ncop' }
local ED_TOKENS = { 'ed', 'nced' }

local function short_song_tag(raw, norm, token_set)
    local t = tokens(norm)
    if #t == 0 then return false end
    if song_token(t[#t], token_set) and #t > 1 then return true end
    if not song_token(t[1], token_set) then return false end
    if #t == 1 then return true end
    local all_fillers = true
    for k = 2, #t do
        if not (SONG_FILLERS[t[k]] or t[k]:match('^%d+$') or t[k]:match('^v%d+$')) then
            all_fillers = false
            break
        end
    end
    if all_fillers then return true end
    -- a separator right after the tag: "OP - Title", "ED: Title", "OP (Title)"
    local lowered = raw:lower()
    for _, p in ipairs(token_set) do
        if lowered:match('^%s*' .. p .. '%d*%s*[%-:|%(%[~]') then return true end
    end
    return false
end

-- Category from the chapter name alone. "intro" is returned as a separate
-- tag because it means the opening in some releases and the cold open in
-- others; classify() resolves it with the rest of the chapter list.
function M.name_category(title)
    if title == nil then return nil end
    local raw = tostring(title)
    local norm = M.normalize(raw)
    if norm == '' then return nil end
    local content = has_any(norm, CONTENT_MARKERS)

    if has_any(norm, PREVIEW_PHRASES) or has_substring(raw, PREVIEW_RAW) then
        if not has_phrase(norm, 'scene') then return 'preview' end
    end
    if has_any(norm, RECAP_PHRASES) or has_substring(raw, RECAP_RAW) then
        return 'recap'
    end
    if has_any(norm, PROLOGUE_PHRASES) or has_substring(raw, PROLOGUE_RAW) then
        return 'prologue'
    end
    -- opening first: "Opening Credits" must not fall into the generic
    -- "credits" ending phrase
    if has_any(norm, OPENING_PHRASES) or has_substring(raw, OPENING_RAW)
        or short_song_tag(raw, norm, OP_TOKENS) then
        if content then return nil end
        return 'opening'
    end
    if has_any(norm, ENDING_PHRASES) or has_substring(raw, ENDING_RAW)
        or short_song_tag(raw, norm, ED_TOKENS) then
        if content then return nil end
        return 'ending'
    end
    if has_phrase(norm, 'intro') or has_phrase(norm, 'intro start') then
        if content then return nil end
        return 'intro'
    end
    return nil
end

local function merged(opts)
    local o = {}
    for k, v in pairs(M.DEFAULTS) do o[k] = v end
    for k, v in pairs(opts or {}) do
        if v ~= nil then o[k] = v end
    end
    return o
end

-- True when most chapters share one length: automatic "every N seconds"
-- splits, where a chapter of song length means nothing. The last chapter
-- is left out because it is the remainder of the split.
local function evenly_cut(lens, n)
    if n < 5 then return false end
    local sorted = {}
    for i = 1, n - 1 do sorted[#sorted + 1] = lens[i] end
    table.sort(sorted)
    local median = sorted[math.floor((#sorted + 1) / 2)]
    local same = 0
    for i = 1, n - 1 do
        if math.abs(lens[i] - median) <= 5 then same = same + 1 end
    end
    return same >= 0.75 * (n - 1)
end

-- chapters: mpv chapter-list ({ {time=, title=}, ... }, sorted by time)
-- duration: file duration in seconds (0/nil when unknown)
-- returns { categories = {[i] = cat}, sources = {[i] = "name"|"length"} }
function M.classify(chapters, duration, opts)
    local o = merged(opts)
    local cats, src = {}, {}
    chapters = chapters or {}
    local n = #chapters
    duration = tonumber(duration) or 0
    if n == 0 then return { categories = cats, sources = src } end

    local starts, lens = {}, {}
    for i = 1, n do
        local s = tonumber(chapters[i].time) or 0
        local e = (chapters[i + 1] and tonumber(chapters[i + 1].time)) or duration
        starts[i] = s
        lens[i] = (e and e > s) and (e - s) or 0
    end

    -- pass 1: names
    local named_opening, named_ending = false, false
    for i = 1, n do
        local c = M.name_category(chapters[i].title)
        if c then
            cats[i], src[i] = c, 'name'
            if c == 'opening' then named_opening = true end
            if c == 'ending' then named_ending = true end
        end
    end
    for i = 1, n do
        if cats[i] == 'intro' then
            if named_opening or (lens[i] > 0 and lens[i] > o.intro_max) then
                cats[i] = 'prologue'
            else
                cats[i] = 'opening'
                named_opening = true
            end
        end
    end

    local function generic(i)
        return cats[i] == nil and M.is_generic(chapters[i].title)
    end
    local function is_song(i)
        return generic(i) and lens[i] >= o.song_min and lens[i] <= o.song_max
    end

    -- pass 2: chapter lengths (unnamed chapter lists only)
    if o.heuristics and not named_opening and not named_ending and n >= 3
        and duration >= o.episode_min and duration <= o.episode_max then
        local songs = 0
        for i = 1, n do if is_song(i) then songs = songs + 1 end end
        -- evenly cut chapters (mkvmerge "every 90 s" ...) carry no structure
        if songs > 0 and songs <= 4 and not evenly_cut(lens, n) then
            local op_limit = math.min(o.op_window, duration * o.op_window_ratio)
            local op = nil
            for i = 1, n - 1 do
                if starts[i] <= op_limit and is_song(i) then
                    op = i
                    -- cold open of song length followed by the OP: the OP
                    -- is the last song-length chapter of the run
                    while op + 1 < n and is_song(op + 1) and starts[op + 1] <= op_limit do
                        op = op + 1
                    end
                    break
                end
            end
            if op then cats[op], src[op] = 'opening', 'length' end

            local ed = nil
            for i = n, 2, -1 do
                if i ~= op and is_song(i)
                    and (starts[i] + lens[i]) >= duration * o.ed_window_ratio then
                    ed = i
                    break
                end
            end
            -- ED followed by a song-length C-part: the ED comes first
            while ed and ed - 1 > (op or 1) and is_song(ed - 1)
                and (starts[ed - 1] + lens[ed - 1]) >= duration * o.ed_window_ratio do
                ed = ed - 1
            end
            if ed then cats[ed], src[ed] = 'ending', 'length' end
        end
    end

    -- a short, unnamed last chapter right after the ending is the preview
    if o.heuristics and n >= 2 and cats[n - 1] == 'ending' and generic(n)
        and lens[n] >= o.preview_min and lens[n] <= o.preview_max then
        cats[n], src[n] = 'preview', 'length'
    end

    return { categories = cats, sources = src }
end

-- One line for the log: "2=opening(length) 5=ending(name)"
function M.describe(result)
    local parts = {}
    local idx = {}
    for i in pairs(result.categories or {}) do idx[#idx + 1] = i end
    table.sort(idx)
    for _, i in ipairs(idx) do
        parts[#parts + 1] = string.format('%d=%s(%s)', i, result.categories[i],
            (result.sources and result.sources[i]) or '?')
    end
    return table.concat(parts, ' ')
end

return M
