local total=0
local function eq(a,b) assert(a==b,tostring(a)..' ~= '..tostring(b)) end
local function test(name,fn) fn(); total=total+1; print('ok thumbfast: '..name) end

-- Regression targets:
--  1) the storyboard fallback path once called file_load() as a nil global
--     and killed the script at every file without usable storyboard data
--     ("attempt to call global 'file_load'" -> Destroying client handle);
--  2) once storyboards fall back for a path, the property observer must not
--     re-attempt storyboards for that same path (hot loop via idle ticks);
--  3) a fresh path must re-attempt storyboards.

local function cleanup()
    _G.file_load = nil
    _G.subprocess = nil
end

local function harness(props)
    -- deployed thumbfast.conf enables network=yes; emulate that in options
    local h={props={
        ['platform']='linux',
        ['media-controls']=nil,
        ['path']=nil,
        ['stream-open-filename']=nil,
        ['user-data/mpv/ytdl/path']='/usr/bin/yt-dlp',
        ['user-data/mpv/ytdl/json-subprocess-result']=nil,
    }}
    if props then for k,v in pairs(props) do h.props[k]=v end end
    h.subprocess_calls = {}    -- recorded subprocess/overlay async calls
    h.observers = {}
    h.events = {}
    h.messages = {}
    h.idle = nil

    local function get(k,d) local v=h.props[k]; if v==nil then return d end; return v end
    local function observe(name, _, fn) h.observers[name]=fn end
    local function register_event(kind, fn) h.events[#h.events+1]={kind=kind,fn=fn} end
    local function add_timer() return {
        is_enabled=function() return false end,
        kill=function() end,
        resume=function() end,
    } end

    mp={log=function() end,
        msg={info=function() end,warn=function() end,error=function() end,
             verbose=function() end,debug=function() end,trace=function() end},
        get_time=function() return 0 end,
        get_property=get,get_property_native=get,get_property_bool=get,
        get_property_number=function(k,d) local v=h.props[k]; if v==nil then return d end; return v end,
        set_property=function(k,v) h.props[k]=v end,
        del_property=function(k) h.props[k]=nil end,
        command_native_async=function(args,cb)
            if type(args)=='table' and args.name=='subprocess' then
                h.subprocess_calls[#h.subprocess_calls+1]={args=args,cb=cb}
            end
            return true end,
        command_native=function(args,cb)
            if type(args)=='table' and args.name=='subprocess' then
                h.subprocess_calls[#h.subprocess_calls+1]={args=args,cb=cb}
            end
            return true end,
        commandv=function() end,
        observe_property=observe,unobserve_property=function() end,
        register_event=register_event,
        register_script_message=function(_,fn) h.messages[#h.messages+1]=fn end,
        register_idle=function(fn) h.idle=fn end,
        add_periodic_timer=add_timer,
        add_timeout=add_timer,
        add_hook=function() end,
        abort_async_command=function() end,
        find_config_file=function() return nil end,
        get_opt=function() return nil end}
    package.loaded['mp.utils']=nil
    package.preload['mp.utils']=function() return {
        getpid=function() return 777 end,
        file_info=function() return nil end,
        format_json=function() return '{}' end,
        parse_json=function() return nil end, -- storyboard json unusable -> falls back
    } end
    package.loaded['mp.options']=nil
    package.preload['mp.options']=function() return {
        read_options=function(o) o.network=true end,
    } end
    dofile('scripts/thumbfast.lua')
    return h
end

local function open_youtube_stream(h, url, open_filename)
    -- thumbfast only sees state through its own observer-fed cache
    h.observers['path']('path',url)
    h.observers['stream-open-filename']('stream-open-filename',open_filename)
    h.observers['user-data/mpv/ytdl/path']('user-data/mpv/ytdl/path','/usr/bin/yt-dlp')
end

test('thumbfast loads and registers without a global file_load leak',function()
    local h=harness()
    local file_load_registered
    for _,ev in ipairs(h.events) do
        if ev.kind=='file-loaded' then file_load_registered=ev.fn end
    end
    eq(type(file_load_registered),'function')
    assert(_G.file_load==nil,'file_load must stay a local, not a global')
    eq(type(h.idle),'function') -- watch_changes registered on idle
    cleanup()
end)

test('storyboard fallback calls file_load instead of crashing the script',function()
    local h=harness({['path']='https://www.youtube.com/watch?v=abc'})
    open_youtube_stream(h,'https://www.youtube.com/watch?v=abc','edl://reproxy')
    -- hook sets the subprocess result; update_property parses no usable
    -- storyboard json and falls back to the regular thumbnailing path
    h.observers['user-data/mpv/ytdl/json-subprocess-result']('user-data/mpv/ytdl/json-subprocess-result',
        {status=0,stdout='<invalid json>'})
    eq(#h.subprocess_calls,0,'fallback must not spawn anything synchronously')
    assert(_G.file_load==nil,'file_load must stay local after fallback')
    cleanup()
end)

test('same path after fallback does not re-attempt storyboards',function()
    local h=harness({['path']='https://www.youtube.com/watch?v=abc'})
    open_youtube_stream(h,'https://www.youtube.com/watch?v=abc','edl://reproxy')
    local fire=function()
        h.observers['user-data/mpv/ytdl/json-subprocess-result']('user-data/mpv/ytdl/json-subprocess-result',
            {status=0,stdout='<invalid json>'})
    end
    fire()
    eq(#h.subprocess_calls,0)
    fire()
    eq(#h.subprocess_calls,0,'same path must not retry storyboards after falling back')
    cleanup()
end)

test('different path re-attempts storyboards after a fallback',function()
    local h=harness({['path']='https://www.youtube.com/watch?v=abc'})
    open_youtube_stream(h,'https://www.youtube.com/watch?v=abc','edl://reproxy')
    h.observers['user-data/mpv/ytdl/json-subprocess-result']('user-data/mpv/ytdl/json-subprocess-result',
        {status=0,stdout='<invalid json>'})
    eq(#h.subprocess_calls,0)
    -- hook clears the result for the next file; new path must be attempted
    h.props['user-data/mpv/ytdl/json-subprocess-result']=nil
    h.observers['path']('path','https://www.youtube.com/watch?v=def')
    h.observers['stream-open-filename']('stream-open-filename','edl://reproxy2')
    h.observers['user-data/mpv/ytdl/json-subprocess-result']('user-data/mpv/ytdl/json-subprocess-result',nil)
    eq(#h.subprocess_calls,1,'new path must attempt storyboards again')
    -- failed yt-dlp exec for the new path: callback must fall back, not crash
    local call=h.subprocess_calls[1]
    assert(call and call.cb,'ytdl exec must be captured with a callback')
    call.cb(false,nil,'exit')
    assert(_G.file_load==nil)
    cleanup()
end)

test('registered file-loaded event handler runs clean twice',function()
    local h=harness()
    local load_event
    for _,ev in ipairs(h.events) do
        if ev.kind=='file-loaded' then load_event=ev.fn end
    end
    eq(type(load_event),'function')
    load_event()
    load_event()
    cleanup()
end)
