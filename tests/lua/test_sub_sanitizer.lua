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
        getpid = function() return 4242 end,
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

test('SRT keeps the tags mpv renders and strips stray ones', function()
    local _, ss = load_script()
    eq('<i>lean</i> <b>shout</b> <u>u</u> <s>s</s>', ss.sanitize_content('<i>lean</i> <b>shout</b> <u>u</u> <s>s</s>', 'srt'))
    eq('<font color="#ffff00">line</font>', ss.sanitize_content('<font color="#ffff00">line</font>', 'srt'))
    eq('quiet yellow', ss.sanitize_content('<span style="x">quiet</span> <c.yellow>yellow</c>', 'srt'))
    eq('<I>caps</I>', ss.sanitize_content('<I>caps</I>', 'srt'))
end)

test('ASS dialogue: tags libass would show are stripped, blocks and \\h stay', function()
    local _, ss = load_script()
    local head = 'Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,'
    eq(head .. '{\\i1}text{\\i0} a\\hb', ss.sanitize_content(head .. '{\\i1}<i>text</i>{\\i0} a\\hb', 'ass'))
end)

test('clean content is left untouched', function()
    local _, ss = load_script()
    eq('Dialogue: plain line', ss.sanitize_content('Dialogue: plain line'))
    eq('00:00:05,000 --> 00:00:08,000', ss.sanitize_content('00:00:05,000 --> 00:00:08,000'))
    eq('{\\\an8}top text', ss.sanitize_content('{\\\an8}top text'))
end)

test('entity names are matched case-insensitively, hex with X too', function()
    local _, ss = load_script()
    eq(RLM .. 'A', ss.decode_entities('&#X200F;A'))
    eq(RLM .. 'B', ss.decode_entities('&RLM;B'))
    eq(NBSP .. 'C', ss.decode_entities('&Nbsp;C'))
    eq('&', ss.decode_entities('&AMP;'))
end)

test('double-encoded entities decode fully', function()
    local _, ss = load_script()
    eq(RLM .. 'x', ss.decode_entities('&amp;rlm;x'))
    eq(NBSP, ss.decode_entities('&amp;nbsp;'))
    eq(RLM, ss.decode_entities('&amp;#8207;'))
    eq('&', ss.decode_entities('&amp;amp;'))
end)

test('a missing ";" is accepted for common names only', function()
    local _, ss = load_script()
    eq('a' .. NBSP .. ' b', ss.decode_entities('a&nbsp b'))
    eq('x' .. RLM, ss.decode_entities('x&rlm'))
    eq(RLM .. ' y', ss.decode_entities('&#8207 y'))
    eq('R&D and AT&T', ss.decode_entities('R&D and AT&T'))
    eq('&nbspX', ss.decode_entities('&nbspX'))     -- not a separate word: left alone
    eq('&hellip', ss.decode_entities('&hellip'))   -- rare names need their ";"
end)

local SAMPLE_ASS = table.concat({
    '[Script Info]',
    'Title: Tom &amp; Jerry; the &rlm; stays in headers',
    'PlayResX: 1280',
    '',
    '[V4+ Styles]',
    'Style: Sign,DejaVu Serif,60,&H0000FFFF,&H000000FF,&H00400000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,7,0,0,0,1',
    '',
    '[Events]',
    'Dialogue: 1,0:00:00.00,0:00:05.00,Sign,,0,0,0,,{\\pos(200,130)\\frz12\\c&H0000FF&}OPEN 24H',
    'Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,&rlm;مرحباً&nbsp;بك{\\i1}!{\\i0}\\h&#x200F;',
    'Comment: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,&rlm;kept as written',
    '',
}, '\r\n')

test('ASS: only Dialogue text changes; headers, styles, comments, tags stay', function()
    local _, ss = load_script()
    local out = ss.sanitize_content(SAMPLE_ASS, 'ass')
    local before, after = {}, {}
    for line in SAMPLE_ASS:gmatch('[^\n]*\n') do before[#before + 1] = line end
    for line in out:gmatch('[^\n]*\n') do after[#after + 1] = line end
    eq(#before, #after)
    for i = 1, #before do
        if i ~= 10 then eq(before[i], after[i]) end
    end
    eq('Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,' .. RLM .. 'مرحباً' .. NBSP
        .. 'بك{\\i1}!{\\i0}\\h' .. RLM .. '\r\n', after[10])
end)

test('the trigger fires on entities and stray tags, not on honest text', function()
    local _, ss = load_script()
    eq(true, ss.looks_unsanitized('and &rlm; then'))
    eq(true, ss.looks_unsanitized('&#1573;'))
    eq(true, ss.looks_unsanitized('see <i>this</i>'))
    eq(false, ss.looks_unsanitized('AT&T costs 5$'))
    eq(false, ss.looks_unsanitized('plain dialogue'))
    eq(false, ss.looks_unsanitized('a < b and c > d'))
    eq(true, ss.looks_unsanitized('&RLM;x'))
    eq(true, ss.looks_unsanitized('&#X200F;x'))
    eq(true, ss.looks_unsanitized('a&nbsp b'))
    eq(false, ss.looks_unsanitized('R&D'))
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

-- ── encodings (2026-11-20 audit): never write UTF-8 into a legacy file ──

local function sanitized_output(h)
    for _, cmd in ipairs(h.commands) do
        if cmd[1] == 'sub-add' then return read_file(cmd[2]) end
    end
    return nil
end

local function run_external(name, bytes, props)
    local h, ss = load_script()
    for k, v in pairs(props or {}) do h.props[k] = v end
    local source = write_temp(name, bytes)
    h.props['current-tracks/sub'] = {
        id = 1, external = true, ['external-filename'] = source,
        codec = name:match('%.ass$') and 'ass' or 'subrip',
    }
    h.messages['sub-sanitize']()
    return sanitized_output(h), ss
end

local CUE = '1\r\n00:00:01,000 --> 00:00:03,000\r\n'
-- مرحبا in Windows-1256
local CP1256_MARHABA = '\227\209\205\200\199'

local function utf16le(utf8)
    local _, ss = load_script()
    local out = {'\255\254'}
    for ch in utf8:gmatch('[%z\1-\127\194-\244][\128-\191]*') do
        local cp = ch:byte(1)
        if #ch == 2 then cp = (cp % 32) * 64 + ch:byte(2) % 64 end
        out[#out + 1] = string.char(cp % 256, math.floor(cp / 256))
    end
    return table.concat(out)
end

test('encoding detection: BOMs, UTF-8, Windows-1256, unknown legacy', function()
    local h, ss = load_script()
    eq('utf-16le', ss.detect_encoding('\255\254a\0'))
    eq('utf-16be', ss.detect_encoding('\254\255\0a'))
    eq('utf-8', ss.detect_encoding('\239\187\191&rlm;مرحبا'))
    eq('utf-8', ss.detect_encoding('plain'))
    eq('cp1256', ss.detect_encoding('&rlm;' .. CP1256_MARHABA .. ' ' .. CP1256_MARHABA))
    eq(nil, ss.detect_encoding('caf\233 &rlm;'))  -- Latin-1, not Arabic
    h.props['sub-codepage'] = '+cp1256'
    eq('cp1256', ss.detect_encoding('caf\233'))
end)

test('Windows-1256: entities are written back as 1256 bytes, Arabic untouched', function()
    local out = run_external('w1256.srt', CUE .. '&rlm;' .. CP1256_MARHABA .. '&nbsp;x\r\n')
    eq(CUE .. '\254' .. CP1256_MARHABA .. '\160x\r\n', out)
end)

test('Windows-1256: numeric entities map to 1256, unrepresentable ones to "?"', function()
    local out, ss = run_external('w1256n.srt', CUE .. CP1256_MARHABA .. '&#1604;&#x1F600;\r\n')
    eq(CUE .. CP1256_MARHABA .. '\225?\r\n', out)
    eq(false, ss.is_utf8(out))
end)

test('UTF-16 with a BOM is converted to UTF-8 and cleaned', function()
    local out = run_external('u16.srt', utf16le(CUE .. '&rlm;مرحبا\r\n'))
    eq(CUE .. RLM .. 'مرحبا\r\n', out)
end)

test('a UTF-8 BOM is kept', function()
    local out = run_external('bom.srt', '\239\187\191' .. CUE .. '&rlm;x\r\n')
    eq('\239\187\191' .. CUE .. RLM .. 'x\r\n', out)
end)

test('an unknown legacy encoding is left alone, not turned into mixed garbage', function()
    local out = run_external('latin1.srt', CUE .. 'caf\233 &rlm;\r\n')
    eq(nil, out)
end)

-- ── temp files and streams (2026-11-20 audit) ──────────────────────────

local function exists(path)
    local fh = io.open(path, 'rb')
    if fh then fh:close() return true end
    return false
end

local function added_paths(h)
    local paths = {}
    for _, cmd in ipairs(h.commands) do
        if cmd[1] == 'sub-add' then paths[#paths + 1] = cmd[2] end
    end
    return paths
end

local function embedded(h, id, body)
    h.on_subprocess = function(t)
        local out = t.args[#t.args]
        local fh = assert(io.open(out, 'wb'))
        fh:write(body)
        fh:close()
    end
    h.props['current-tracks/sub'] = { id = id, external = false, ['ff-index'] = id, codec = 'subrip' }
    h.messages['sub-sanitize']()
end

test('temp names: unique per track, carry the pid, never the video name', function()
    local h, ss = load_script()
    h.props['path'] = write_temp('Show: Ep?01*.mkv', 'video')
    embedded(h, 2, '1\n00:00:01,000 --> 00:00:02,000\n&rlm;a\n')
    embedded(h, 3, '1\n00:00:01,000 --> 00:00:02,000\n&rlm;b\n')
    local paths = added_paths(h)
    eq(2, #paths)
    assert(paths[1] ~= paths[2], 'two tracks share a file: ' .. paths[1])
    for _, path in ipairs(paths) do
        local name = path:match('([^/\\]+)$')
        assert(name:find('^mpv%-sub%-sanitizer%-4242%-%x+%.sanitized%.srt$'), name)
        assert(not name:find('[<>:"|%?%*]'), name)
    end
end)

test('the ffmpeg extraction file is unique and removed after reading', function()
    local h, ss = load_script()
    h.props['path'] = write_temp('extract.mkv', 'video')
    local raw
    h.on_subprocess = function(t)
        raw = t.args[#t.args]
        local fh = assert(io.open(raw, 'wb'))
        fh:write('1\n00:00:01,000 --> 00:00:02,000\n&rlm;a\n')
        fh:close()
    end
    h.props['current-tracks/sub'] = { id = 2, external = false, ['ff-index'] = 2, codec = 'subrip' }
    h.messages['sub-sanitize']()
    assert(raw:match('mpv%-sub%-sanitizer%-4242%-%x+%-extract%.srt$'), raw)
    eq(false, exists(raw))
end)

test('temp copies are deleted when the file ends and when mpv quits', function()
    for _, event in ipairs({'end-file', 'shutdown'}) do
        local h, ss = load_script()
        local source = write_temp('cleanup_' .. event .. '.srt', '1\n00:00:01,000 --> 00:00:02,000\n&rlm;x\n')
        h.props['current-tracks/sub'] = { id = 1, external = true, ['external-filename'] = source, codec = 'subrip' }
        h.messages['sub-sanitize']()
        local path = added_paths(h)[1]
        eq(true, exists(path))
        h.events[event]()
        eq(false, exists(path))
        eq(true, exists(source))  -- the user's own file is never touched
    end
end)

test('save_next_to_video writes beside the video and keeps the file', function()
    local h, ss = load_script()
    ss.options.save_next_to_video = true
    local video = write_temp('beside.mkv', 'video')
    h.props['path'] = video
    local source = write_temp('beside.srt', '1\n00:00:01,000 --> 00:00:02,000\n&rlm;x\n')
    h.props['current-tracks/sub'] = { id = 5, external = true, ['external-filename'] = source, codec = 'subrip' }
    h.messages['sub-sanitize']()
    local path = added_paths(h)[1]
    eq(video:gsub('%.tmp$', ''):gsub('[^/\\]+$', '') , path:gsub('[^/\\]+$', ''))
    assert(path:find('%.5%.sanitized%.srt$'), path)
    h.events['end-file']()
    eq(true, exists(path))
    os.remove(path)
end)

test('network sources are skipped: nothing downloaded, nothing added', function()
    for _, video in ipairs({'https://cdn.example/v.mkv', 'edl://https://x/a;https://x/b', 'ytdl://abc'}) do
        local h, ss = load_script()
        h.props['path'] = video
        h.props['current-tracks/sub'] = { id = 2, external = false, ['ff-index'] = 2, codec = 'subrip' }
        h.messages['sub-sanitize']()
        eq(0, #h.subprocess)
        eq(0, #added_paths(h))
    end
    local h, ss = load_script()
    h.props['current-tracks/sub'] = { id = 1, external = true, codec = 'subrip',
        ['external-filename'] = 'https://example.com/subs/ar.srt' }
    h.messages['sub-sanitize']()
    eq(0, #added_paths(h))
    eq(false, ss.is_network('/media/Data/show.mkv'))
    eq(false, ss.is_network('C:\\Videos\\show.mkv'))
    eq(false, ss.is_network('file:///media/show.mkv'))
end)

test('temp dir: TEMP, then TMP (Windows), then TMPDIR, then /tmp', function()
    local _, ss = load_script()
    local function env(t) return function(k) return t[k] end end
    eq('C:\\Users\\User\\AppData\\Local\\Temp', ss.temp_dir(env({TEMP = 'C:\\Users\\User\\AppData\\Local\\Temp', TMPDIR = '/x'})))
    eq('C:\\Temp', ss.temp_dir(env({TMP = 'C:\\Temp', TMPDIR = '/x'})))
    eq('/run/user/1000', ss.temp_dir(env({TMPDIR = '/run/user/1000'})))
    eq('/tmp', ss.temp_dir(env({})))
end)

-- ── asynchronous extraction (2026-11-20 audit) ─────────────────────────

-- A deferred command_native_async: the test decides when ffmpeg "finishes".
local function async_harness(body)
    local h, ss = load_script()
    h.pending = {}
    mp.command_native_async = function(t, cb)
        h.subprocess[#h.subprocess + 1] = t
        h.pending[#h.pending + 1] = function(ok)
            local out = t.args[#t.args]
            if ok then
                local fh = assert(io.open(out, 'wb'))
                fh:write(body)
                fh:close()
            end
            cb(ok, {status = ok and 0 or -1, stderr = ''}, nil)
            return out
        end
    end
    h.props['path'] = write_temp('async.mkv', 'video')
    h.props['current-tracks/sub'] = { id = 2, external = false, ['ff-index'] = 2, codec = 'subrip' }
    return h, ss
end

local ASYNC_BODY = '1\n00:00:01,000 --> 00:00:02,000\n&rlm;x\n'

test('async: extraction does not block and is killed with the file', function()
    local h, ss = async_harness(ASYNC_BODY)
    h.observers['sub-text']('sub-text', '&rlm;x')
    eq(1, #h.subprocess)
    eq(true, h.subprocess[1].playback_only)
    eq(0, #added_paths(h))                     -- nothing yet: ffmpeg still running
    h.observers['sub-text']('sub-text', '&rlm;x again')
    eq(1, #h.subprocess)                       -- never started twice
    local raw = h.pending[1](true)
    eq('select', h.commands[#h.commands][3])
    eq(false, exists(raw))
end)

test('async: a result for a file that is no longer playing is dropped', function()
    local h, ss = async_harness(ASYNC_BODY)
    h.observers['sub-text']('sub-text', '&rlm;x')
    h.props['path'] = write_temp('next.mkv', 'other video')
    local raw = h.pending[1](true)
    eq(0, #added_paths(h))
    eq(false, exists(raw))
end)

test('async: a track the user left meanwhile is added, not selected', function()
    local h, ss = async_harness(ASYNC_BODY)
    h.observers['sub-text']('sub-text', '&rlm;x')
    h.props['current-tracks/sub'] = { id = 3, external = false, codec = 'subrip' }
    h.pending[1](true)
    eq('auto', h.commands[#h.commands][3])
end)

test('async: a failed or killed ffmpeg adds nothing', function()
    local h, ss = async_harness(ASYNC_BODY)
    h.observers['sub-text']('sub-text', '&rlm;x')
    h.pending[1](false)
    eq(0, #added_paths(h))
end)

-- ── right-to-left punctuation (ASS) ───────────────────────────────────
-- Invented lines. libass keeps a leading U+200F line left-to-right, so the
-- fix is U+202B (RTL embedding) at each line start and after each \N.

local RLE = '\226\128\171'  -- U+202B
local HEAD = 'Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,'

local function ass(lines)
    local out = {
        '[Script Info]', 'ScriptType: v4.00+', '',
        '[V4+ Styles]',
        'Style: Default,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1',
        '', '[Events]',
    }
    for _, line in ipairs(lines) do
        out[#out + 1] = line:match('^%u%a+:') and line or HEAD .. line
    end
    return table.concat(out, '\r\n') .. '\r\n'
end

test('rtl: a plain track gets U+202B per line and after \\N, nothing else moves', function()
    local _, ss = load_script()
    local src = ass({
        'نعم، أنت محق.',
        '{\\an8}«سامي» هنا!',
        '3 رجال وصلوا?',
        'Rami، هل أنت هنا؟',
        'حسناً.\\Nلنذهب الآن!',
        'Fine.\\Nحسناً، "ليلى".',
        'Dialogue: 1,0:00:00.00,0:00:05.00,Default,,0,0,0,,{\\pos(10,10)}لافتة.',
        'Comment: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,ملاحظة.',
    })
    local out, report = ss.fix_rtl_punctuation(src)
    eq('plain', report.class)
    eq(5, report.changed)
    eq(ass({
        RLE .. 'نعم، أنت محق.',
        '{\\an8}' .. RLE .. '«سامي» هنا!',
        RLE .. '3 رجال وصلوا?',
        'Rami، هل أنت هنا؟',
        RLE .. 'حسناً.\\N' .. RLE .. 'لنذهب الآن!',
        'Fine.\\N' .. RLE .. 'حسناً، "ليلى".',
        'Dialogue: 1,0:00:00.00,0:00:05.00,Default,,0,0,0,,{\\pos(10,10)}لافتة.',
        'Comment: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,ملاحظة.',
    }), out)
end)

test('rtl: a leading U+200F alone does not count as marked (libass ignores it)', function()
    local _, ss = load_script()
    local out, report = ss.fix_rtl_punctuation(ass({
        RLM .. 'نعم، أنت محق.', RLM .. '"ليلى"!', RLM .. 'Rami، هل أنت هنا؟', LRM .. 'Rami، هنا.',
    }))
    eq('plain', report.class)
    -- a leading RLM is itself a strong right-to-left character, LRM a left-to-right one
    eq(ass({
        RLE .. RLM .. 'نعم، أنت محق.', RLE .. RLM .. '"ليلى"!', RLE .. RLM .. 'Rami، هل أنت هنا؟', LRM .. 'Rami، هنا.',
    }), out)
end)

test('rtl: already marked tracks (U+202B first or U+200F last) are left alone', function()
    local _, ss = load_script()
    for _, src in ipairs({
        ass({ RLE .. 'نعم، أنت محق.', RLE .. '«سامي» هنا!', 'بلا علامة.' }),
        ass({ 'نعم، أنت محق.' .. RLM, '"ليلى"!' .. RLM, 'بلا علامة.' }),
    }) do
        local out, report = ss.fix_rtl_punctuation(src)
        eq('marked', report.class)
        eq(src, out)
    end
end)

test('rtl: a pre-reversed track (end punctuation typed first) is left alone', function()
    local _, ss = load_script()
    local src = ass({ '.نعم، أنت محق', '!انتبه', '?هل أنت بخير', '،قال ذلك', '."ليلى"', 'نعم، أنت محق.' })
    local out, report = ss.fix_rtl_punctuation(src)
    eq('pre-reversed', report.class)
    eq(5, report.votes['pre-reversed'])
    eq(src, out)
end)

test('rtl: Latin-only and tied tracks stay byte for byte', function()
    local _, ss = load_script()
    local latin = ass({ 'Yes, you are right.', '"Rami"!', '{\\an8}Who? Me?\\NFine.' })
    local out, report = ss.fix_rtl_punctuation(latin)
    eq('none', report.class)
    eq(latin, out)
    local tied = ass({ 'نعم، أنت محق.', '.نعم، أنت محق' })
    out, report = ss.fix_rtl_punctuation(tied)
    eq('tie', report.class)
    eq(tied, out)
end)

test('rtl: override blocks are never edited, even when they hold \\N-like text', function()
    local _, ss = load_script()
    local out = ss.fix_rtl_punctuation(ass({ '{\\fnArial\\N}نعم، أنت محق.', '{note: x}"ليلى"!' }))
    eq(ass({ '{\\fnArial\\N}' .. RLE .. 'نعم، أنت محق.', '{note: x}' .. RLE .. '"ليلى"!' }), out)
end)

test('rtl: Arabic sub-text triggers ASS tracks only', function()
    local _, ss = load_script()
    eq(true, ss.has_arabic('نعم.'))
    eq(false, ss.has_arabic('Yes. "Rami"! « » ' .. RLM))
    for _, case in ipairs({ { 'ass', 1 }, { 'subrip', 0 } }) do
        local h = load_script()
        local source = write_temp('rtl.' .. case[1], case[1] == 'ass' and ass({ 'نعم، أنت محق.' })
            or '1\n00:00:00,000 --> 00:00:05,000\nنعم، أنت محق.\n')
        h.props['current-tracks/sub'] = {
            id = 1, external = true, ['external-filename'] = source, codec = case[1],
        }
        h.observers['sub-text']('sub-text', 'نعم، أنت محق.')
        eq(case[2], #added_paths(h))
    end
end)

test('rtl: an Arabic ASS file is fixed once; its cleaned copy is not reprocessed', function()
    local h = load_script()
    local source = write_temp('rtl-once.ass', ass({ 'نعم، أنت محق.' }))
    h.props['current-tracks/sub'] = {
        id = 1, external = true, ['external-filename'] = source, codec = 'ass', title = 'Arabic',
    }
    h.observers['sub-text']('sub-text', 'نعم، أنت محق.')
    local added = added_paths(h)
    eq(1, #added)
    eq(ass({ RLE .. 'نعم، أنت محق.' }), read_file(added[1]))
    assert(h.osds[1].text:find('right-to-left', 1, true), h.osds[1].text)
    h.props['current-tracks/sub'] = {
        id = 2, external = true, ['external-filename'] = added[1], codec = 'ass',
    }
    h.observers['sub-text']('sub-text', 'نعم، أنت محق.')
    eq(1, #added_paths(h))
end)

test('rtl: SRT gets no marks; entity fixes still apply', function()
    local _, ss = load_script()
    local srt = '1\n00:00:00,000 --> 00:00:05,000\n&rlm;نعم، أنت محق.\n'
    eq('1\n00:00:00,000 --> 00:00:05,000\n' .. RLM .. 'نعم، أنت محق.\n', ss.sanitize_content(srt, 'srt'))
end)

test('rtl: a Windows-1256 ASS track is converted whole to UTF-8, then marked', function()
    -- U+202B has no Windows-1256 byte, so the whole file goes out as UTF-8
    local marhaba = 'مرحبا'
    local out, ss = run_external('rtl1256.ass', ass({
        '&rlm;' .. CP1256_MARHABA .. ' ' .. CP1256_MARHABA .. '.',
        CP1256_MARHABA .. '\\N' .. CP1256_MARHABA .. '!',
    }))
    eq(ass({
        RLE .. RLM .. marhaba .. ' ' .. marhaba .. '.',
        RLE .. marhaba .. '\\N' .. RLE .. marhaba .. '!',
    }), out)
    eq('utf-8', ss.detect_encoding(out))
end)

test('rtl: a Windows-1256 ASS track needing no marks stays 1256', function()
    -- pre-reversed: end punctuation typed first, so no mark and no conversion
    local out = run_external('rev1256.ass', ass({
        '.&rlm;' .. CP1256_MARHABA .. ' ' .. CP1256_MARHABA,
        '!' .. CP1256_MARHABA .. ' ' .. CP1256_MARHABA,
    }))
    eq(ass({
        '.\254' .. CP1256_MARHABA .. ' ' .. CP1256_MARHABA,
        '!' .. CP1256_MARHABA .. ' ' .. CP1256_MARHABA,
    }), out)
end)

print('Sub sanitizer tests passed: ' .. total)
