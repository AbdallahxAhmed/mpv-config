local total=0
local function eq(a,b) assert(a==b,tostring(a)..' ~= '..tostring(b)) end
local function test(name,fn) fn(); total=total+1; print('ok hook: '..name) end
local function fixture()
    local v={format_id='video',vcodec='avc1.640028',acodec='none',width=1920,height=1080,fps=30,url='https://media.example/video'}
    local low={format_id='en-low',vcodec='none',acodec='opus',language='en',abr=64,format_note='low',url='https://media.example/en-low'}
    local high={format_id='en-high',vcodec='none',acodec='opus',language='en',abr=256,format_note='high',url='https://media.example/en-high'}
    local ar={format_id='ar',vcodec='none',acodec='opus',language='ar',abr=128,format_note='medium',url='https://media.example/ar'}
    return {extractor='youtube',duration=100,title='Test video',formats={v,low,ar,high},requested_formats={v,low}}
end
local function run(config)
    config=config or {}
    local h={json=fixture(),calls={},commands={},hooks={},props={
        ['stream-open-filename']=config.url or 'https://youtu.be/video',
        ['options/ytdl-format']=config.format_empty and '' or 'bestvideo[height<=?1080]+bestaudio/best',
        ['options/ytdl-raw-options']=config.raw or {},['options/vid']='auto',
        aid=config.aid or 'auto',sid=config.sid or 'auto',
        ['option-info/ytdl-format/set-from-commandline']=config.explicit_format or false,
        ['mpv-version']=config.mpv_version or 'mpv v0.42.0'}}
    if config.live then h.json.is_live=true end
    if config.other then h.json.extractor='other' end
    local function get(k,d) local v=h.props[k]; if v==nil then return d end; return v end
    local function set(k,v) h.props[k]=v end
    local log=setmetatable({}, {__index=function() return function() end end})
    mp={log=function() end,get_property=get,get_property_native=get,get_property_bool=get,
        set_property=set,set_property_native=set,set_property_bool=set,set_property_number=set,
        del_property=function(k) h.props[k]=nil end,
        find_config_file=function(name)
            if name=='scripts/modules/stream_policy.lua' and not config.no_helper then return name end
            -- One nil result, not zero return values in table.insert arguments.
            return nil
        end,
        command_native=function(c)
            if c[1]=='expand-path' then return '/config/yt-dlp.exe' end
            -- Regression: the subprocess table must use the universal
            -- "name" key (mpv <= 0.41 releases reject "_name" as invalid
            -- parameter) and must NOT carry "_name".
            assert(c.name=='subprocess')
            assert(c._name==nil)
            -- Snapshot args at call time: the hook reuses/mutates a single
            -- command table, so storing a reference would erase history.
            local snap={} for i,v in ipairs(c.args) do snap[i]=v end
            h.calls[#h.calls+1]=snap
            -- mpv >= 0.40 returns null when the process cannot be spawned.
            if config.broken_then_good and c.args[1]=='/broken/yt-dlp' then
                -- Friend's-observed shape: command itself fails, err string
                -- compensates — exec() must normalize, not crash.
                return nil, 'init'
            end
            if config.nil_subprocess then return nil end
            return {status=0,stdout='fixture',stderr=''}
        end,
        commandv=function(...) h.commands[#h.commands+1]={...} end,
        add_hook=function(name,priority,fn) h.hooks[name]=h.hooks[name] or {}; table.insert(h.hooks[name],{priority,fn}) end}
    for _,name in ipairs({'mp.utils','mp.msg','mp.options'}) do package.loaded[name]=nil end
    package.preload['mp.utils']=function() return {parse_json=function() return h.json end,
        file_info=function(path)
            if path=='yt-dlp' then return {is_file=true} end
            if config.broken_then_good and path=='/broken/yt-dlp' then return {is_file=true} end
            return nil
        end} end
    package.preload['mp.msg']=function() return log end
    package.preload['mp.options']=function() return {read_options=function(o, ident)
        ident = ident or ''
        if ident=='stream_quality' then
            if config.default_quality ~= nil then o.default_quality = tostring(config.default_quality) end
            return
        end
        o.ytdl_path = config.broken_then_good and '/broken/yt-dlp:yt-dlp' or 'yt-dlp'
        if config.all_audio then o.best_audio_per_language=false end
        if config.all_subs then o.youtube_subs_on_demand=false end
    end} end
    dofile('scripts/ytdl_hook.lua')
    table.sort(h.hooks.on_load,function(a,b) return a[1]<b[1] end)
    for _,hook in ipairs(h.hooks.on_load) do hook[2]() end
    h.edl=h.props['stream-open-filename']
    function h:has_arg(arg) for _,v in ipairs(self.calls[1] or {}) do if v==arg then return true end end; return false end
    return h
end
test('one extractor call, fewer audio streams, video and default language intact',function()
    local h=run(); eq(#h.calls,1)
    assert(h.edl:find('https://media.example/video',1,true))
    assert(h.edl:find('https://media.example/en-high',1,true))
    assert(h.edl:find('https://media.example/ar',1,true))
    assert(not h.edl:find('https://media.example/en-low',1,true))
    assert(h.edl:find('w=1920,h=1080,fps=30',1,true))
    assert(h.props['file-local-options/aid']~='no')
    assert(not h.edl:find('audio only',1,true))
    local _,defaults=h.edl:gsub('flags=default',''); eq(defaults,2)
    assert(#h.edl < #run({all_audio=true}).edl)
end)
test('no automatic caption enumeration at startup',function()
    local h=run(); assert(not h:has_arg('--write-srt')); assert(not h:has_arg('--sub-langs'))
    assert(h:has_arg('--no-playlist')); assert(h:has_arg('--format')); eq(#h.commands,0)
end)
local function format_arg(h)
    for i,v in ipairs(h.calls[1] or {}) do if v=='--format' then return (h.calls[1])[i+1] end end
    return nil
end
test('default quality: hook builds the cap from stream_quality.conf',function()
    -- mpv.conf no longer pins ytdl-format: an empty option + saved default
    -- (720 here) must reproduce the old template cap exactly.
    local h=run({format_empty=true, default_quality=720})
    eq(format_arg(h), 'bestvideo[height<=?720]+bestaudio/best[height<=?720]/best')
end)
test('default quality 0 / unset: yt-dlp keeps its own preference order',function()
    -- no cap: the hook must NOT pass --format (mirrors the upstream default path)
    local h=run({format_empty=true, default_quality=0})
    eq(format_arg(h), nil)
end)
test('default quality never overrides an explicitly set ytdl-format',function()
    -- mpv.conf.user (or the Quality button) keeps precedence
    local h=run({default_quality=720})
    eq(format_arg(h), 'bestvideo[height<=?1080]+bestaudio/best')
end)
test('raw subtitle request and numeric sid retain upstream behavior',function()
    assert(run({raw={['write-auto-subs']='',['sub-langs']='ar'}}):has_arg('--write-srt'))
    assert(run({sid='2'}):has_arg('--write-srt'))
    assert(run({all_subs=true}):has_arg('--write-srt'))
end)
test('explicit format and saved numeric aid are not reinterpreted',function()
    for _,cfg in ipairs({{explicit_format=true},{aid='3'},{all_audio=true}}) do
        assert(run(cfg).edl:find('https://media.example/en-low',1,true))
    end
end)
test('live and non-YouTube formats are untouched',function()
    assert(run({live=true}).edl:find('https://media.example/en-low',1,true))
    local h=run({other=true,url='ytdl://https://other.example/video'})
    assert(h.edl:find('https://media.example/en-low',1,true)); assert(h:has_arg('--write-srt'))
end)
test('missing helper safely retains upstream playback',function()
    local h=run({no_helper=true}); eq(#h.calls,1)
    assert(h.edl:find('https://media.example/en-low',1,true)); assert(h:has_arg('--write-srt'))
end)
test('metadata cache and visibility are per-file',function()
    local h=run(); eq(h.props['user-data/mpv/ytdl/source-url'],'https://youtu.be/video')
    eq(h.props['user-data/mpv/ytdl/is-youtube'],true)
    eq(h.props['user-data/mpv/ytdl/json-subprocess-result'].stdout,'fixture')
    eq(#h.json.formats,4); eq(h.json.requested_formats[2].format_id,'en-low')
    for _,hook in ipairs(h.hooks.on_after_end_file) do hook[2]() end
    eq(h.props['user-data/mpv/ytdl/source-url'],nil); eq(h.props['user-data/mpv/ytdl/is-youtube'],nil)
end)
test('local files never invoke yt-dlp',function() eq(#run({url='/media/local.mkv'}).calls,0) end)
test('mpv >= 0.40 null subprocess result normalizes instead of crashing',function()
    -- Regression: on mpv >= 0.40 a spawn failure (bad ytdl_path candidate)
    -- makes command_native return null; without normalization the hook
    -- crashed at 'if result.killed_by_us' ("client removed during hook
    -- handling", then "Failed to recognize file format").
    local h=run({nil_subprocess=true})
    eq(h.props['user-data/mpv/ytdl/json-subprocess-result'].status,-1)
    eq(h.props['user-data/mpv/ytdl/json-subprocess-result'].error_string,'init')
    -- stream-open-filename untouched and no EDL rewrite: a graceful
    -- "youtube-dl failed" path, not a script crash.
    eq(h.edl,'https://youtu.be/video')
end)
test('a broken configured candidate does not stall the search',function()
    -- Regression: the known-paths loop used to break on the FIRST existing
    -- file even when its spawn failed (init), so every later candidate —
    -- including the PATH-based bare name — was never tried.
    local h=run({broken_then_good=true})
    eq(#h.calls,2)
    eq(h.calls[1][1],'/broken/yt-dlp')
    eq(h.calls[2][1],'yt-dlp')
    eq(h.props['user-data/mpv/ytdl/json-subprocess-result'].stdout,'fixture')
    assert(h.edl:find('https://media.example/video',1,true))
end)
test('EDL program_id gated by mpv build (0.41 release emits none, master does)',function()
    -- Regression: release binaries up to mpv 0.41 reject EDL
    -- "!track_meta,...,program_id=" with "Unknown or duplicate parameter"
    -- once per track (37 warnings for a 4K YouTube track list).
    eq(run({mpv_version='mpv v0.41.0'}).edl:find('program_id',1,true),nil)
    eq(run({mpv_version='mpv 0.41.0'}).edl:find('program_id',1,true),nil)
    assert(run({mpv_version='mpv v0.41.0-809-g84e8b2a'}).edl:find('program_id',1,true))
    assert(run({mpv_version='mpv v0.42.0'}).edl:find('program_id',1,true))
    assert(run().edl:find('program_id',1,true))
end)
test('fast quality switch: flagged URL skips extraction entirely',function()
    -- The toolbar pre-resolves the stream URL and marks it via
    -- user-data/mpv/ytdl/fast-url; on_load must consume the flag and open
    -- the URL as-is — zero yt-dlp spawns, zero re-signed URLs.
    local h=run()
    local before=#h.calls
    -- a fast switch loads the raw URL again: mpv re-populates
    -- stream-open-filename with it before on_load runs
    h.props['user-data/mpv/ytdl/fast-url']='https://youtu.be/video'
    h.props['stream-open-filename']='https://youtu.be/video'
    for _,hook in ipairs(h.hooks.on_load) do hook[2]() end
    eq(#h.calls,before)
    eq(h.props['user-data/mpv/ytdl/fast-url'],nil)
    -- a different or stale flag never bypasses extraction
    local h2=run()
    h2.props['user-data/mpv/ytdl/fast-url']='https://media.example/other-video'
    for _,hook in ipairs(h2.hooks.on_load) do hook[2]() end
    eq(#h2.calls,1)
end)
print('Hook tests passed: '..total)
