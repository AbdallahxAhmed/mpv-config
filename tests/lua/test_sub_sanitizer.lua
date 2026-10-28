-- sub_sanitizer: HTML entities and stray tags in subtitle tracks.
-- 2026-10-28 report: Arabic subs with literal `&rlm;`, `&lrm;`, `&nbsp;`
-- rendered the entities as on-screen text on both platforms.
local total = 0
local function eq(a, b) assert(a == b, tostring(a) .. ' ~= ' .. tostring(b)) end
local function test(name, fn) fn(); total = total + 1; print('ok sub_sanitizer: ' .. name) end

-- unpack: LuaJIT exposes the global, Lua 5.2+ moves it into table.
local unpack = unpack or table.unpack

local here = debug.getinfo(1, 'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or './') .. '/'
if not here:match('[/\\]$') and here ~= './' then here = here .. '/' end

local SCRIPT = here .. '../../scripts/sub_sanitizer.lua'

local RLM = '\226\128\143'  -- U+200F right-to-left mark
local LRM = '\226\128\142'  -- U+200E left-to-right mark
local NBSP = '\194\160'     -- U+00A0

local function load_script()
    _G.mp = nil
    local h = {
        props = {}, osds = {}, events = {}, observers = {}, commands = {},
        messages = {}, subprocess = {},
    }
    _G.mp = {
        log = function() end,
        msg = {info = function() end, warn = function() end, error = function() end},
        get_property = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        get_property_native = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        set_property = function(k, v) h.props[k] = v end,
        osd_message = function(text, duration) h.osds[#h.osds + 1] = {text = text, duration = duration} end,
        commandv = function(...) h.commands[#h.commands + 1] = {...} end,
        command_native = function(t)
            if type(t) == 'table' and t.name == 'subprocess' then
                h.subprocess[#h.subprocess + 1] = t
                if h.on_subprocess then h.on_subprocess(t) end
                return {status = 0, stdout = '', stderr = ''}
            end
            return nil
        end,
        register_event = function(name, fn) h.events[name] = fn end,
        observe_property = function(name, typ, fn) h.observers[name] = fn end,
        register_script_message = function(name, fn) h.messages[name] = fn end,
    }
    package.loaded['mp.options'] = nil
    package.preload['mp.options'] = function() return {read_options = function() end} end
    package.loaded['mp.utils'] = nil
    package.preload['mp.utils'] = function() return {
        file_info = function(p)
            local fh = io.open(p, 'r')
            if not fh then return nil end
            fh:close()
            return {is_file = true}
        end,
        join_path = function(a, b) return a:gsub('[/\\]$', '') .. '/' .. b end,
        format_time = function() return '' end,
    } end
    dofile(SCRIPT)
    return h, _G.sub_sanitizer
end

-- ── pure text rules ───────────────────────────────────────────────────

test('the reported entity line decodes with a real RTL mark', function()
    local _, ss = load_script()
    -- the exact on-screen garbage from the 2026-10-28 report
    local out = ss.decode_entities('&rlm;شيئاً أخيراً؟')
    eq(RLM, out:sub(1, 3))
    eq(false, out:find('&rlm;', 1, true) ~= nil)
    assert(out:find('شيئاً', 1, true), out)
end)

test('known entities decode preserving their intent', function()
    local _, ss = load_script()
    eq('A&B "q" <x> ' .. NBSP .. 'end', ss.decode_entities('A&amp;B &quot;q&quot; &lt;x&gt; &nbsp;end'))
    eq(RLM .. LRM, ss.decode_entities('&rlm;&lrm;'))
    eq('mix' .. RLM, ss.decode_entities('mix&rlm;'))
end)

test('numeric and hex entities become their characters', function()
    local _, ss = load_script()
    -- U+0625 إ then U+0644 ل: two-byte and two-byte UTF-8 forms
    eq('\216\165\217\132', ss.decode_entities('&#1573;&#x644;'))
    eq('q', ss.decode_entities('&#113;'))
    -- out-of-range codepoints are garbage: stripped
    eq('', ss.decode_entities('&#999999999;'))
end)

test('unknown entities are stripped', function()
    local _, ss = load_script()
    eq('ab', ss.decode_entities('a&bogus;b'))
    eq('', ss.decode_entities('&unknown;'))
end)

test('raw HTML tags are stripped, ASS blocks and hard spaces stay', function()
    local _, ss = load_script()
    eq('{\\i1}text{\\i0} a\\hb', ss.sanitize_content('{\\i1}<i>text</i>{\\i0} a\\hb'))
    eq('shout', ss.sanitize_content('<b>shout</b>'))
    eq('line', ss.sanitize_content('<font size="42">line</font>'))
    eq('quiet', ss.sanitize_content('<span style="x">quiet</span>'))
end)

test('clean content is left untouched', function()
    local _, ss = load_script()
    eq('Dialogue: plain line', ss.sanitize_content('Dialogue: plain line'))
    eq('00:00:05,000 --> 00:00:08,000', ss.sanitize_content('00:00:05,000 --> 00:00:08,000'))
    eq('{\\\an8}top text', ss.sanitize_content('{\\\an8}top text'))
end)

test('the trigger fires on entities and stray tags, not on honest text', function()
    local _, ss = load_script()
    eq(true, ss.looks_unsanitized('and &rlm; then'))
    eq(true, ss.looks_unsanitized('&#1573;'))
    eq(true, ss.looks_unsanitized('see <i>this</i>'))
    eq(false, ss.looks_unsanitized('AT&T costs 5$'))
    eq(false, ss.looks_unsanitized('plain dialogue'))
    eq(false, ss.looks_unsanitized('a < b and c > d'))
end)

-- ── track orchestration ───────────────────────────────────────────────

local function write_temp(name, content)
    local dir = (os.getenv('TEMP') or os.getenv('TMPDIR') or '/tmp'):gsub('[/\\]$', '')
    local path = dir .. '/sub_sanitizer_test_' .. name .. '_' .. total .. '.tmp'
    local fh = assert(io.open(path, 'wb'))
    fh:write(content)
    fh:close()
    return path
end

local function read_file(path)
    local fh = assert(io.open(path, 'r'))
    local content = fh:read('*a')
    fh:close()
    return content
end

test('an external track is cleaned and selected, original kept', function()
    local h, ss = load_script()
    local source = write_temp('source.srt', '1\n00:00:05,000 --> 00:00:08,000\n&rlm;مرحبا\n')
    h.props['current-tracks/sub'] = {
        id = 1, external = true, ['external-filename'] = source, title = 'Arabic',
        codec = 'subrip',
    }
    h.observers['sub-text']('sub-text', '&rlm;مرحبا')
    -- cleaned file selected through sub-add, nothing removed
    local added = 0
    for _, cmd in ipairs(h.commands) do
        if cmd[1] == 'sub-add' then
            added = added + 1
            eq('select', cmd[3])
            assert(cmd[2]:find('.sanitized.srt', 1, true), cmd[2])
            eq('1\n00:00:05,000 --> 00:00:08,000\n' .. RLM .. 'مرحبا\n', read_file(cmd[2]))
        end
        if cmd[1] == 'sub-remove' then
            error('the original track must stay available')
        end
    end
    eq(1, added)
    eq(1, #h.osds)
end)

test('the same track is sanitized only once', function()
    local h, ss = load_script()
    local source = write_temp('source2.srt', '1\n00:00:05,000 --> 00:00:08,000\n&rlm;x\n')
    h.props['current-tracks/sub'] = {
        id = 1, external = true, ['external-filename'] = source, codec = 'subrip',
    }
    h.observers['sub-text']('sub-text', '&rlm;x')
    h.observers['sub-text']('sub-text', '&rlm;x again')
    local added = 0
    for _, cmd in ipairs(h.commands) do
        if cmd[1] == 'sub-add' then added = added + 1 end
    end
    eq(1, added)
end)

test('an embedded track is extracted with ffmpeg, then cleaned', function()
    local h, ss = load_script()
    local video = write_temp('episode.mkv', 'fake video bytes')
    local extract_path
    h.on_subprocess = function(t)
        -- the ffmpeg contract the autosubsync extraction also relies on
        local args = t.args
        for i = 1, #args - 1 do
            if args[i] == '-map' then
                eq('0:2', args[i + 1])
            elseif args[i] == '-f' then
                extract_path = args[i + 2]
                eq('srt', args[i + 1])
            end
        end
        local fh = assert(io.open(extract_path, 'w'))
        fh:write('1\n00:00:05,000 --> 00:00:08,000\n&#x644;y\n')
        fh:close()
    end
    h.props['path'] = video
    h.props['current-tracks/sub'] = {
        id = 2, external = false, ['ff-index'] = 2, codec = 'subrip', title = 'Arabic',
    }
    h.observers['sub-text']('sub-text', '&#x644;y')
    assert(extract_path, 'ffmpeg was not asked for srt output')
    local added = 0
    for _, cmd in ipairs(h.commands) do
        if cmd[1] == 'sub-add' then
            added = added + 1
            eq('1\n00:00:05,000 --> 00:00:08,000\n\217\132y\n', read_file(cmd[2]))  -- ل
        end
    end
    eq(1, added)
end)

test('a clean track never triggers a sanitize pass', function()
    local h, ss = load_script()
    local source = write_temp('clean.srt', '1\n00:00:05,000 --> 00:00:08,000\nمرحبا\n')
    h.props['current-tracks/sub'] = {
        id = 1, external = true, ['external-filename'] = source, codec = 'subrip',
    }
    h.observers['sub-text']('sub-text', 'مرحبا')
    eq(0, #h.commands)
end)

test('the manual sanitize message force-processes the current track', function()
    local h, ss = load_script()
    local source = write_temp('manual.srt', '1\n00:00:05,000 --> 00:00:08,000\n&amp; x\n')
    h.props['current-tracks/sub'] = {
        id = 1, external = true, ['external-filename'] = source, codec = 'subrip',
    }
    -- no sub-text ever rendered anything; the message is the testing seam
    h.messages['sub-sanitize']()
    local added = 0
    for _, cmd in ipairs(h.commands) do
        if cmd[1] == 'sub-add' then added = added + 1 end
    end
    eq(1, added)
end)

print('Sub sanitizer tests passed: ' .. total)