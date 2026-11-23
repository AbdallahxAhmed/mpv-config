-- sub_sanitizer.lua — repairs subtitles that render HTML entities as text.
--
-- 2026-10-28 report: Arabic subs (embedded MKV tracks and external files)
-- shipped with literal `&rlm;`, `&lrm;`, `&nbsp;` and broken raw tags, and
-- libass renders those verbatim: `&rlm;شيئاً أخيراً؟` shows the entity.
--
-- How it works: sub-text is observed; the first rendered line that still
-- contains entity-like text trips a one-shot sanitize of the WHOLE track.
-- External tracks are read directly; embedded tracks are extracted with
-- ffmpeg (same contract the autosubsync script uses), cleaned, written to
-- a new file, and selected with sub-add — the original track stays
-- available. Entities decode to their real Unicode (RTL marks survive as
-- U+200F/U+200E so bidi keeps working), case-insensitively, through double
-- encoding (`&amp;rlm;`) and a missing ";" on common names; unknown `&x;`
-- entities and stray tags are stripped. Only subtitle text is touched: SRT
-- cue text (keeping the <i> <b> <u> <s> <font> tags mpv renders) and the Text
-- field of ASS Dialogue lines outside `{\...}` blocks; `\h` stays.
--
-- Options (script-opts/sub_sanitizer.conf):
--   enabled=yes            set to no to disable the automatic pass
--   save_next_to_video=no  write `<video>.<track>.sanitized.<ext>` next to
--                          the video (kept) instead of a temp file
--
-- Temp files are named mpv-sub-sanitizer-<pid>-<track hash>.sanitized.<ext>
-- (no two tracks or mpv instances collide, nothing from the video name ends
-- up in it) and are deleted when the file ends and when mpv quits. Network
-- paths (http, edl, ytdl, ...) are skipped: extracting would download them.
--   remove_original=no     unload the original track after the swap
--
-- The `sub-sanitize` script message force-processes the current track;
-- it exists so the pass is verifiable headless (and scriptable).

local msg = require 'mp.msg'
local options = require 'mp.options'
local utils = require 'mp.utils'

local o = {
    enabled = true,
    save_next_to_video = false,
    remove_original = false,
}
options.read_options(o, "sub_sanitizer")

local state = { processed = {} }

-- Decode to real characters, never delete the marks: `&rlm;` is a bidi
-- control the author wanted (U+200F), so it becomes the actual codepoint.
-- Names are matched case-insensitively (`&RLM;`, `&Nbsp;` occur in the wild).
local NAMED_ENTITIES = {
    rlm = "\226\128\143",   -- U+200F RIGHT-TO-LEFT MARK
    lrm = "\226\128\142",   -- U+200E LEFT-TO-RIGHT MARK
    nbsp = "\194\160",      -- U+00A0 NO-BREAK SPACE
    zwj = "\226\128\141",   -- U+200D ZERO WIDTH JOINER
    zwnj = "\226\128\140",  -- U+200C ZERO WIDTH NON-JOINER
    amp = "&",
    quot = '"',
    apos = "'",
    lt = "<",
    gt = ">",
    hellip = "\226\128\166", -- …
    ndash = "\226\128\147",  -- –
    mdash = "\226\128\148",  -- —
    laquo = "\194\171",      -- «
    raquo = "\194\187",      -- »
    lsquo = "\226\128\152", rsquo = "\226\128\153",
    ldquo = "\226\128\156", rdquo = "\226\128\157",
}

-- Broken converters drop the closing ";" of these; elsewhere a bare "&name"
-- is ordinary text ("R&D", "AT&T") and is left alone.
local SEMICOLON_OPTIONAL = {
    nbsp = true, rlm = true, lrm = true, amp = true, lt = true, gt = true, quot = true,
}

-- SRT tags mpv itself renders; anything else is stray markup. libass shows
-- every <tag> in ASS text verbatim, so ASS keeps none.
local SRT_TAGS = { i = true, b = true, u = true, s = true, font = true }

-- mpv's LuaJIT lacks the utf8 library; emit the byte sequence directly.
local function utf8_encode(cp)
    if cp < 0x80 then
        return string.char(cp)
    elseif cp < 0x800 then
        return string.char(192 + math.floor(cp / 64), 128 + (cp % 64))
    elseif cp < 0x10000 then
        return string.char(
            224 + math.floor(cp / 4096),
            128 + (math.floor(cp / 64) % 64),
            128 + (cp % 64))
    end
    return string.char(
        240 + math.floor(cp / 262144),
        128 + (math.floor(cp / 4096) % 64),
        128 + (math.floor(cp / 64) % 64),
        128 + (cp % 64))
end

local function codepoint(cp)
    if cp and cp > 0 and cp < 0x110000 then return utf8_encode(cp) end
    return ""  -- out-of-range codepoint: rendering garbage
end

local function decode_once(text)
    text = text:gsub("&#[xX](%x+);?", function(hex) return codepoint(tonumber(hex, 16)) end)
    text = text:gsub("&#(%d+);?", function(dec) return codepoint(tonumber(dec)) end)
    text = text:gsub("&(%a%w*)(;?)", function(name, semi)
        local key = name:lower()
        local value = NAMED_ENTITIES[key]
        if value and (semi == ";" or SEMICOLON_OPTIONAL[key]) then return value end
        if semi == ";" then return "" end  -- unknown entity: renders as garbage
        return nil                         -- not an entity: keep the text
    end)
    return text
end

-- Double-encoded entities (`&amp;rlm;`) need a second pass; three is plenty.
local function decode_entities(text)
    for _ = 1, 3 do
        local decoded = decode_once(text)
        if decoded == text then break end
        text = decoded
    end
    return text
end

local function strip_tags(text, keep)
    return (text:gsub("<(/?)(%a[%w%.%-]*)([^>\r\n]*)>", function(_, name)
        if keep and keep[name:lower()] then return nil end
        return ""
    end))
end

local function clean_text(text, keep)
    return strip_tags(decode_entities(text), keep)
end

-- ASS: only the Text field of Dialogue lines, and only outside `{...}`
-- override blocks. Headers, styles, comments and tags stay byte-identical.
local DIALOGUE = "^(Dialogue:" .. string.rep("[^,]*,", 9) .. ")(.*)$"

local function clean_ass_text(text)
    local out, pos = {}, 1
    while true do
        local s, e = text:find("{[^}]*}", pos)
        if not s then
            out[#out + 1] = clean_text(text:sub(pos))
            break
        end
        out[#out + 1] = clean_text(text:sub(pos, s - 1))
        out[#out + 1] = text:sub(s, e)
        pos = e + 1
    end
    return table.concat(out)
end

local function each_line(content, fn)
    local out = {}
    for line in content:gmatch("[^\n]*\n?") do
        if line ~= "" then
            local body, eol = line:match("^(.-)(\r?\n?)$")
            out[#out + 1] = fn(body) .. eol
        end
    end
    return table.concat(out)
end

local function sanitize_content(content, ext)
    if ext == "ass" then
        return each_line(content, function(line)
            local head, text = line:match(DIALOGUE)
            if not head then return line end
            return head .. clean_ass_text(text)
        end)
    end
    -- SRT: cue numbers and timing lines are not text
    return each_line(content, function(line)
        if line:match("^%s*%d+%s*$") or line:find("-->", 1, true) then return line end
        return clean_text(line, SRT_TAGS)
    end)
end

-- sub-text is plain text: mpv already turned the SRT tags it supports into
-- styling, so any tag still visible here is one it shows verbatim.
local function looks_unsanitized(text)
    if type(text) ~= "string" then return false end
    if text:find("&#[xX]%x") or text:find("&#%d") then return true end
    for name, semi in text:gmatch("&(%a%w*)(;?)") do
        local key = name:lower()
        if semi == ";" or (SEMICOLON_OPTIONAL[key] and NAMED_ENTITIES[key]) then return true end
    end
    return text:find("</?%a[%w%.%-]*[^>\r\n]*>") ~= nil
end

-- ── encodings ─────────────────────────────────────────────────────────
-- Entities decode to UTF-8 bytes, so they may only be written into UTF-8.
-- A Windows-1256 file is decoded, cleaned and encoded back to 1256 (it has
-- RLM 0xFE, LRM 0xFD, NBSP 0xA0), unless the right-to-left fix adds U+202B,
-- which 1256 cannot hold: then the whole file is written as UTF-8. UTF-16
-- is converted to UTF-8; any other legacy encoding is left alone rather
-- than turned into mixed garbage.

-- Windows-1256 bytes 0x80..0xFF -> Unicode (generated from Python's codec).
local CP1256 = {
    0x20AC, 0x067E, 0x201A, 0x0192, 0x201E, 0x2026, 0x2020, 0x2021,
    0x02C6, 0x2030, 0x0679, 0x2039, 0x0152, 0x0686, 0x0698, 0x0688,
    0x06AF, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014,
    0x06A9, 0x2122, 0x0691, 0x203A, 0x0153, 0x200C, 0x200D, 0x06BA,
    0x00A0, 0x060C, 0x00A2, 0x00A3, 0x00A4, 0x00A5, 0x00A6, 0x00A7,
    0x00A8, 0x00A9, 0x06BE, 0x00AB, 0x00AC, 0x00AD, 0x00AE, 0x00AF,
    0x00B0, 0x00B1, 0x00B2, 0x00B3, 0x00B4, 0x00B5, 0x00B6, 0x00B7,
    0x00B8, 0x00B9, 0x061B, 0x00BB, 0x00BC, 0x00BD, 0x00BE, 0x061F,
    0x06C1, 0x0621, 0x0622, 0x0623, 0x0624, 0x0625, 0x0626, 0x0627,
    0x0628, 0x0629, 0x062A, 0x062B, 0x062C, 0x062D, 0x062E, 0x062F,
    0x0630, 0x0631, 0x0632, 0x0633, 0x0634, 0x0635, 0x0636, 0x00D7,
    0x0637, 0x0638, 0x0639, 0x063A, 0x0640, 0x0641, 0x0642, 0x0643,
    0x00E0, 0x0644, 0x00E2, 0x0645, 0x0646, 0x0647, 0x0648, 0x00E7,
    0x00E8, 0x00E9, 0x00EA, 0x00EB, 0x0649, 0x064A, 0x00EE, 0x00EF,
    0x064B, 0x064C, 0x064D, 0x064E, 0x00F4, 0x064F, 0x0650, 0x00F7,
    0x0651, 0x00F9, 0x0652, 0x00FB, 0x00FC, 0x200E, 0x200F, 0x06D2,
}
local CP1256_REVERSE, CP1256_ARABIC = {}, {}
for i, cp in ipairs(CP1256) do
    CP1256_REVERSE[cp] = 0x7F + i
    CP1256_ARABIC[0x7F + i] = cp >= 0x0600 and cp <= 0x06FF
end

local function utf8_codepoints(s)
    local cps = {}
    for ch in s:gmatch("[%z\1-\127\194-\244][\128-\191]*") do
        local b1, n = ch:byte(1), #ch
        local cp
        if n == 1 then cp = b1
        elseif n == 2 then cp = (b1 % 32) * 64 + ch:byte(2) % 64
        elseif n == 3 then cp = (b1 % 16) * 4096 + (ch:byte(2) % 64) * 64 + ch:byte(3) % 64
        else cp = (b1 % 8) * 262144 + (ch:byte(2) % 64) * 4096 + (ch:byte(3) % 64) * 64 + ch:byte(4) % 64 end
        cps[#cps + 1] = cp
    end
    return cps
end

local function is_utf8(s)
    local i, n = 1, #s
    while i <= n do
        local c = s:byte(i)
        local len = c < 0x80 and 1 or (c >= 0xC2 and c <= 0xDF) and 2
            or (c >= 0xE0 and c <= 0xEF) and 3 or (c >= 0xF0 and c <= 0xF4) and 4 or nil
        if not len or i + len - 1 > n then return false end
        for k = i + 1, i + len - 1 do
            local cc = s:byte(k)
            if cc < 0x80 or cc > 0xBF then return false end
        end
        i = i + len
    end
    return true
end

local function utf16_to_utf8(s, big_endian)
    local out, i = {}, 3  -- skip the BOM
    local function unit(k)
        local a, b = s:byte(k, k + 1)
        if not b then return nil end
        return big_endian and a * 256 + b or b * 256 + a
    end
    while i <= #s - 1 do
        local u = unit(i)
        i = i + 2
        if u >= 0xD800 and u <= 0xDBFF then
            local lo = unit(i)
            if lo and lo >= 0xDC00 and lo <= 0xDFFF then
                u = 0x10000 + (u - 0xD800) * 1024 + (lo - 0xDC00)
                i = i + 2
            end
        end
        out[#out + 1] = utf8_encode(u)
    end
    return table.concat(out)
end

local function cp1256_to_utf8(s)
    return (s:gsub("[\128-\255]", function(c) return utf8_encode(CP1256[c:byte() - 0x7F]) end))
end

local function utf8_to_cp1256(s)
    local out = {}
    for _, cp in ipairs(utf8_codepoints(s)) do
        if cp < 0x80 then out[#out + 1] = string.char(cp)
        else out[#out + 1] = string.char(CP1256_REVERSE[cp] or 0x3F) end  -- "?" if not in 1256
    end
    return table.concat(out)
end

local function looks_cp1256(s)
    local high, arabic = 0, 0
    for c in s:gmatch("[\128-\255]") do
        high = high + 1
        if CP1256_ARABIC[c:byte()] then arabic = arabic + 1 end
    end
    return arabic >= 4 and arabic * 2 >= high
end

-- "utf-8", "utf-16le", "utf-16be", "cp1256", or nil for an unknown legacy encoding.
local function detect_encoding(content)
    local b1, b2 = content:byte(1, 2)
    if b1 == 0xFF and b2 == 0xFE then return "utf-16le" end
    if b1 == 0xFE and b2 == 0xFF then return "utf-16be" end
    if is_utf8(content) then return "utf-8" end
    local codepage = (mp.get_property("sub-codepage") or ""):lower()
    if codepage:find("1256", 1, true) or looks_cp1256(content) then return "cp1256" end
    return nil
end

-- Decode to UTF-8 for cleaning; returns text and the function that writes it back.
local function to_utf8(content, encoding)
    if encoding == "utf-16le" then return utf16_to_utf8(content, false), nil end
    if encoding == "utf-16be" then return utf16_to_utf8(content, true), nil end
    if encoding == "cp1256" then return cp1256_to_utf8(content), utf8_to_cp1256 end
    return content, nil
end

-- ── right-to-left punctuation (ASS) ───────────────────────────────────
-- libass lays ASS dialogue out left-to-right whenever the style's Encoding
-- is not -1 (VSFilter compatibility), so "نعم، أنت محق." shows its period
-- right of the first word instead of left of the last. A leading U+200F
-- does NOT change that base direction (libass 0.17.5, fribidi 1.0.18); a
-- leading U+202B (RTL embedding) does, per line: after each \N too. Bidi
-- also restarts at every override block, so only the first text segment
-- of a line is covered. SRT needs nothing: mpv lays converted SRT out with
-- automatic direction, and the same line already renders correctly.
--
-- Each Arabic ASS track is classified by majority vote of its dialogue
-- lines, and only class "plain" is changed:
--   marked        lines start with U+202B or end with U+200F: already right
--   pre-reversed  end punctuation typed first (".نعم") so it shows right
--                 under LTR: a fansub workaround, left as it is
--   plain         first strong character Arabic, punctuation or quotes at
--                 an edge, no mark: U+202B goes in front of every line
--                 (and after every \N) whose first strong character is Arabic
--                 or U+200F (the author's own right-to-left request)
-- Signs (\pos, \move, \org, \clip, \p drawings, an Effect, a style named
-- Sign) never vote and are never changed; neither are {\...} blocks.

local RLE = "\226\128\171"  -- U+202B RIGHT-TO-LEFT EMBEDDING

local function in_ranges(cp, ranges)
    for i = 1, #ranges, 2 do
        if cp >= ranges[i] and cp <= ranges[i + 1] then return true end
    end
    return false
end

-- Bidi class AL, coarsely: the Arabic blocks minus their digits, number
-- signs, the comma, and combining marks (harakat, which belong to the
-- letter before them).
local ARABIC_BLOCKS = { 0x0600, 0x06FF, 0x0750, 0x077F, 0x08A0, 0x08FF, 0xFB50, 0xFDFF, 0xFE70, 0xFEFF }
local ARABIC_NUMERIC = { 0x0600, 0x060A, 0x060C, 0x060C, 0x0660, 0x066C, 0x06F0, 0x06F9, 0xFEFF, 0xFEFF }
local COMBINING = { 0x0610, 0x061A, 0x064B, 0x065F, 0x0670, 0x0670, 0x06D6, 0x06ED, 0x08D3, 0x08FF, 0xFE00, 0xFE0F }
-- Bidi class L, coarsely: Latin, Greek, Cyrillic, Armenian, Indic, CJK, Hangul.
local LTR_LETTERS = {
    0x0041, 0x005A, 0x0061, 0x007A, 0x00C0, 0x00D6, 0x00D8, 0x00F6, 0x00F8, 0x024F,
    0x0370, 0x058F, 0x0900, 0x1FFF, 0x3040, 0x9FFF, 0xAC00, 0xD7AF,
}
local BIDI_CONTROLS = { 0x200E, 0x200F, 0x202A, 0x202E, 0x2066, 0x2069 }
local SPACES = { [0x09] = true, [0x20] = true, [0xA0] = true }
-- What a pre-reversed line starts with: end punctuation, never a quote.
local END_PUNCT = {
    [0x2E] = true, [0x21] = true, [0x3F] = true, [0x2C] = true, [0x3A] = true, [0x3B] = true,
    [0x060C] = true, [0x061F] = true, [0x2026] = true,
}

local function direction(cp)
    if in_ranges(cp, ARABIC_BLOCKS) and not in_ranges(cp, ARABIC_NUMERIC)
        and not in_ranges(cp, COMBINING) then
        return "rtl"
    end
    if in_ranges(cp, LTR_LETTERS) then return "ltr" end
    return nil
end

local function is_digit(cp)
    return (cp >= 0x30 and cp <= 0x39) or (cp >= 0x0660 and cp <= 0x0669) or (cp >= 0x06F0 and cp <= 0x06F9)
end

-- Punctuation, quotes and symbols: what bidi places by its neighbours.
local function is_neutral(cp)
    return not direction(cp) and not is_digit(cp) and not SPACES[cp]
        and not in_ranges(cp, BIDI_CONTROLS) and not in_ranges(cp, COMBINING)
end

-- Facts about one visual line of plain text (no blocks, \h as a space).
local function scan_line(visible)
    local cps = utf8_codepoints(visible)
    local first, last, strong, arabic
    local leading_rle = false
    for i, cp in ipairs(cps) do
        if cp == 0x202B and not first then leading_rle = true end
        -- RLM and LRM are strong characters too: "\u200FRami، ..." is an
        -- Arabic sentence whose author asked for right-to-left
        if cp == 0x200F then strong = strong or "rtl" end
        if cp == 0x200E then strong = strong or "ltr" end
        if not SPACES[cp] and not in_ranges(cp, BIDI_CONTROLS) then
            first = first or i
            last = i
            local d = direction(cp)
            strong = strong or d
            arabic = arabic or d == "rtl"
        end
    end
    if not arabic then return { strong = strong } end
    local trailing_rlm = false
    for i = last + 1, #cps do
        if cps[i] == 0x200F then trailing_rlm = true end
    end
    local vote
    if leading_rle or trailing_rlm then
        vote = "marked"
    elseif END_PUNCT[cps[first]] and not END_PUNCT[cps[last]] then
        vote = "pre-reversed"
    elseif strong == "rtl" and (is_neutral(cps[first]) or is_neutral(cps[last])) then
        vote = "plain"
    end
    return { strong = strong, vote = vote, marked = leading_rle or trailing_rlm }
end

-- The Text field as visual lines: each a list of {text=} / {tag=} pieces,
-- with the "\N" that ended it in .sep. Joining them back is byte-identical.
local function ass_visual_lines(text)
    local lines, cur, pos = {}, {}, 1
    while pos <= #text + 1 do
        local s, e = text:find("{[^}]*}", pos)
        local chunk = text:sub(pos, (s or #text + 1) - 1)
        local p = 1
        while true do
            local a, b = chunk:find("\\N", p, true)
            if not a then break end
            cur[#cur + 1] = { text = chunk:sub(p, a - 1) }
            cur.sep = "\\N"
            lines[#lines + 1] = cur
            cur = {}
            p = b + 1
        end
        cur[#cur + 1] = { text = chunk:sub(p) }
        if not s then break end
        cur[#cur + 1] = { tag = text:sub(s, e) }
        pos = e + 1
    end
    lines[#lines + 1] = cur
    return lines
end

local function visible_text(line)
    local parts = {}
    for _, piece in ipairs(line) do
        if piece.text then parts[#parts + 1] = (piece.text:gsub("\\h", " ")) end
    end
    return table.concat(parts)
end

local function join_lines(lines)
    local out = {}
    for _, line in ipairs(lines) do
        for _, piece in ipairs(line) do out[#out + 1] = piece.text or piece.tag end
        out[#out + 1] = line.sep or ""
    end
    return table.concat(out)
end

local DIALOGUE_FIELDS = "^Dialogue:[^,]*,[^,]*,[^,]*,([^,]*),[^,]*,[^,]*,[^,]*,[^,]*,([^,]*),$"

local function is_sign(head, text)
    local style, effect = head:match(DIALOGUE_FIELDS)
    if not style then return true end  -- unexpected layout: hands off
    if style:lower():find("sign", 1, true) or effect:match("%S") then return true end
    for block in text:gmatch("{[^}]*}") do
        if block:find("\\pos%s*%(") or block:find("\\move%s*%(") or block:find("\\org%s*%(")
            or block:find("\\i?clip%s*%(") or block:find("\\p%s*[1-9]") then
            return true
        end
    end
    return false
end

-- Calls fn(head, lines) for every dialogue (non-sign) line of an ASS file;
-- fn returns new lines or nil. Everything else stays byte-identical.
local function each_dialogue(content, fn)
    return each_line(content, function(line)
        local head, text = line:match(DIALOGUE)
        if not head or is_sign(head, text) then return line end
        local lines = fn(ass_visual_lines(text))
        return lines and head .. join_lines(lines) or line
    end)
end

local RTL_CLASSES = { "marked", "pre-reversed", "plain" }

local function count_rtl_votes(content)
    local votes = { marked = 0, ["pre-reversed"] = 0, plain = 0 }
    each_dialogue(content, function(lines)
        for _, line in ipairs(lines) do
            local facts = scan_line(visible_text(line))
            if facts.vote then votes[facts.vote] = votes[facts.vote] + 1 end
        end
    end)
    return votes
end

-- The class with the most votes; "tie" when two share it, "none" if no votes.
local function majority(votes)
    local class, best = "none", 0
    for _, name in ipairs(RTL_CLASSES) do
        if votes[name] > best then
            class, best = name, votes[name]
        elseif votes[name] == best and best > 0 then
            class = "tie"
        end
    end
    return class
end

-- U+202B in front of the first text segment of every unmarked visual line
-- whose first strong character is right-to-left. Returns content, count.
local function insert_rtl_marks(content)
    local changed = 0
    local fixed = each_dialogue(content, function(lines)
        local touched = false
        for _, line in ipairs(lines) do
            local facts = scan_line(visible_text(line))
            if facts.strong == "rtl" and not facts.marked then
                for _, piece in ipairs(line) do
                    if piece.text and piece.text:find("%S") then
                        piece.text = RLE .. piece.text
                        touched = true
                        break
                    end
                end
            end
        end
        if touched then
            changed = changed + 1
            return lines
        end
    end)
    return fixed, changed
end

-- Returns the content (U+202B added for class plain) and a report:
-- { class = "none"|"tie"|<one of RTL_CLASSES>, votes = {...}, changed = n }.
local function fix_rtl_punctuation(content)
    local votes = count_rtl_votes(content)
    local report = { class = majority(votes), votes = votes, changed = 0 }
    if report.class ~= "plain" then return content, report end
    content, report.changed = insert_rtl_marks(content)
    return content, report
end

local function describe_rtl(report)
    local v = report.votes
    return string.format("right-to-left check: %s (marked %d, pre-reversed %d, plain %d); %d dialogue lines changed",
        report.class, v.marked, v["pre-reversed"], v.plain, report.changed)
end

-- sub-text carries plain text: any Arabic letter (U+0600..U+06FF, U+0750..U+077F).
local function has_arabic(text)
    return type(text) == "string" and text:find("[\216-\219\221][\128-\191]") ~= nil
end

-- ── track handling ────────────────────────────────────────────────────

local codec_ext_map = { subrip = "srt", ass = "ass", ssa = "ass" }

local function basename(path)
    return (tostring(path):gsub("\\", "/"):match("([^/]+)$")) or ""
end

local function dirname(path)
    return (tostring(path):gsub("\\", "/"):match("^(.*)/[^/]+$"))
end

-- TEMP/TMP first (Windows), then TMPDIR (POSIX).
local function temp_dir(getenv)
    getenv = getenv or os.getenv
    return getenv("TEMP") or getenv("TMP") or getenv("TMPDIR") or "/tmp"
end

local PID = tostring((utils.getpid and utils.getpid()) or os.time())

-- Short stable hash (djb2) so names stay unique per track without carrying
-- the track's own path, which may hold characters Windows forbids.
local function short_hash(text)
    local h = 5381
    for i = 1, #text do h = (h * 33 + text:byte(i)) % 4294967296 end
    return string.format("%08x", h)
end

-- Safe in a Windows file name: no control characters or <>:"/\|?*.
local function safe_name(text)
    text = text:gsub('[%c<>:"/\\|%?%*]', "_"):gsub("[%. ]+$", "")
    return text:sub(1, 60)
end

-- Any URL-like path except file://: reading it would mean downloading it.
local function is_network(path)
    local scheme = tostring(path or ""):match("^(%a[%w+.%-]*)://")
    return scheme ~= nil and scheme:lower() ~= "file"
end

local temp_files = {}

local function remove_temp_files()
    for path in pairs(temp_files) do
        os.remove(path)
        temp_files[path] = nil
    end
end

local function read_file(path)
    if not path then return nil end
    local fh = io.open(path, "rb")
    if not fh then return nil end
    local content = fh:read("*a")
    fh:close()
    return content
end

local function write_file(path, content)
    local fh = io.open(path, "wb")
    if not fh then return false end
    fh:write(content)
    fh:close()
    return true
end

local function ffmpeg_candidates()
    if os.getenv("HOME") == nil then
        -- Windows: the installer lands ffmpeg next to mpv
        local prog = os.getenv("ProgramFiles") or "C:/Program Files"
        local appdata = os.getenv("APPDATA") or ""
        return {
            prog .. "/mpv/ffmpeg/bin/ffmpeg.exe",
            appdata .. "/mpv/tools/ffmpeg/ffmpeg.exe",
        }
    end
    return {
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        (os.getenv("HOME") or "") .. "/.local/bin/ffmpeg",
    }
end

local function find_ffmpeg()
    for _, candidate in ipairs(ffmpeg_candidates()) do
        local info = utils.file_info(candidate)
        if info and info.is_file then return candidate end
    end
    return "ffmpeg"  -- last resort: whatever PATH provides
end

-- Asynchronous: ffmpeg reads the whole container to reach an interleaved
-- subtitle stream, which must not hold up this script (or compete with
-- playback on a slow disk). playback_only lets mpv kill it on file change.
local function extract_track(track, ext, key, done)
    local video = mp.get_property("path")
    if not video then return done(nil) end
    local raw = utils.join_path(temp_dir(),
        "mpv-sub-sanitizer-" .. PID .. "-" .. short_hash(key) .. "-extract." .. ext)
    local cmd = {
        name = "subprocess",
        playback_only = true,
        capture_stdout = true,
        capture_stderr = true,
        args = {
            find_ffmpeg(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            "-an", "-vn", "-i", video,
            "-map", "0:" .. tostring(track["ff-index"] or track.id),
            "-f", ext, raw,
        },
    }
    local function finish(success, ret)
        local content
        if success and type(ret) == "table" and ret.status == 0 and utils.file_info(raw) then
            content = read_file(raw)
        else
            msg.warn("sub_sanitizer: ffmpeg extraction failed: "
                .. tostring(type(ret) == "table" and (ret.stderr or ret.error_string) or ret))
        end
        os.remove(raw)
        if mp.get_property("path") ~= video then
            msg.info("sub_sanitizer: the file changed during extraction; result dropped")
            return
        end
        done(content)
    end
    if mp.command_native_async then
        mp.command_native_async(cmd, finish)
    else
        finish(true, mp.command_native(cmd))
    end
end

local function output_path(track, ext, key)
    local video = mp.get_property("path") or ""
    if o.save_next_to_video and not is_network(video) then
        local dir = dirname(video)
        if dir and dir ~= "" then
            local base = safe_name(basename(video):gsub("%.[%w]+$", ""))
            return utils.join_path(dir, base .. "." .. tostring(track.id) .. ".sanitized." .. ext), false
        end
    end
    local name = "mpv-sub-sanitizer-" .. PID .. "-" .. short_hash(key) .. ".sanitized." .. ext
    return utils.join_path(temp_dir(), name), true
end

local function track_key(track)
    if track.external and track["external-filename"] then
        return "ext:" .. track["external-filename"]
    end
    local path = mp.get_property("path") or ""
    return "embedded:" .. path .. ":" .. tostring(track["ff-index"] or track.id)
end

-- Clean, write and load one track's text (called once extraction is done).
local function finish_track(track, ext, key, content)
    if not content then return false end

    local encoding = detect_encoding(content)
    if not encoding then
        msg.info("sub_sanitizer: unknown legacy text encoding; track left as it is")
        return false
    end
    local text, write_back = to_utf8(content, encoding)
    local cleaned = sanitize_content(text, ext)
    local entities_fixed = cleaned ~= text
    local rtl = { changed = 0 }
    if ext == "ass" then
        cleaned, rtl = fix_rtl_punctuation(cleaned)
        msg.info("sub_sanitizer: " .. describe_rtl(rtl))
        if rtl.changed > 0 and write_back then
            -- Windows-1256 has no byte for U+202B: the whole file goes out as UTF-8
            write_back = nil
            msg.info("sub_sanitizer: Windows-1256 file converted to UTF-8")
        end
    end
    if cleaned == text then
        msg.info("sub_sanitizer: track is already clean")
        return false
    end
    if write_back then cleaned = write_back(cleaned) end

    local out_path, is_temp = output_path(track, ext, key)
    if not write_file(out_path, cleaned) then
        msg.warn("sub_sanitizer: cannot write " .. out_path)
        return false
    end
    if is_temp then temp_files[out_path] = true end
    -- the copy is Arabic ASS too: selecting it must not start another pass
    state.processed["ext:" .. out_path] = true
    msg.info("sub_sanitizer: cleaned track written to " .. out_path)
    -- the user may have moved to another track while ffmpeg ran: add, don't select
    local current = mp.get_property_native("current-tracks/sub")
    local still_current = type(current) == "table" and current.id == track.id
    mp.commandv("sub-add", out_path, still_current and "select" or "auto",
        (track.title or "subtitles") .. " [cleaned]")
    if o.remove_original then
        mp.commandv("sub-remove", track.id)
    end
    local done = {}
    if entities_fixed then done[#done + 1] = "HTML entities stripped" end
    if rtl.changed > 0 then done[#done + 1] = "right-to-left punctuation fixed" end
    mp.osd_message("Subtitles sanitized: " .. table.concat(done, ", "), 2)
    return true
end

local function sanitize_track(track)
    if type(track) ~= "table" then return false end
    local key = track_key(track)
    if state.processed[key] then return false end
    -- set before the work: sub-text keeps firing while we extract
    state.processed[key] = true

    local ext = codec_ext_map[track.codec]
    if not ext then
        msg.info("sub_sanitizer: unsupported codec: " .. tostring(track.codec))
        return false
    end

    local source = track.external and track["external-filename"] or mp.get_property("path")
    if is_network(source) then
        msg.info("sub_sanitizer: network subtitle source skipped: " .. tostring(source))
        return false
    end

    if track.external then
        finish_track(track, ext, key, read_file(track["external-filename"]))
    else
        extract_track(track, ext, key, function(content) finish_track(track, ext, key, content) end)
    end
    return true
end

-- Any Arabic ASS track is considered (its punctuation may need marks), as
-- is any track with entity-like text. Arabic SRT alone does not trigger:
-- mpv already lays it out with automatic direction.
local function on_sub_text(_, text)
    if not o.enabled then return end
    local track = mp.get_property_native("current-tracks/sub")
    local ass = type(track) == "table" and codec_ext_map[track.codec] == "ass"
    if not looks_unsanitized(text) and not (ass and has_arabic(text)) then return end
    sanitize_track(track)
end

mp.observe_property("sub-text", "string", on_sub_text)
-- mpv drops external tracks when the file ends; their temp copies go too.
mp.register_event("end-file", remove_temp_files)
mp.register_event("shutdown", remove_temp_files)
mp.register_script_message("sub-sanitize", function()
    sanitize_track(mp.get_property_native("current-tracks/sub"))
end)

_G.sub_sanitizer = {
    detect_encoding = detect_encoding,
    is_utf8 = is_utf8,
    temp_dir = temp_dir,
    is_network = is_network,
    temp_files = temp_files,
    decode_entities = decode_entities,
    sanitize_content = sanitize_content,
    fix_rtl_punctuation = fix_rtl_punctuation,
    has_arabic = has_arabic,
    looks_unsanitized = looks_unsanitized,
    sanitize_track = sanitize_track,
    state = state,
    options = o,
}
