-- Real Lua at the mpv boundary: click commands, state, and filter ownership.
local total = 0
local function eq(a,b) if a ~= b then error(debug.traceback('ASSERTION FAILED: '..tostring(a)..' ~= '..tostring(b), 2)) end end
local function test(name,fn) fn(); total=total+1; print('ok toolbar: '..name) end
local label = 'mpv_config_stable_volume'
local normalizer = 'dynaudnorm=f=500:g=15:p=0.95:m=10'
local limiter = 'alimiter=limit=0.9:level=false'
local graph = normalizer..','..limiter
local function filter(g,l,enabled) return {name='lavfi',label=l,enabled=enabled,params={graph=g}} end
local function harness(filters, no_ui, conf)
    conf = conf or {}
    local h={filters=filters or {},messages={},writes=0,sends=0,ui_ready=not no_ui,buttons={},props={},observers={}}
    mp={log=function() end,get_script_name=function() return 'player_toolbar' end,
        find_config_file=function(name)
            if conf.conf_path and name=='script-opts/stream_quality.conf' then return conf.conf_path end
            return nil
        end,
        get_property_native=function(k,d) if k=='af' then return h.filters end; return h.props[k] or d end,
        get_property_number=function(k,d) return tonumber(h.props[k]) or d end,
        get_property=function(k,d) return h.props[k] or d end,
        set_property_native=function(k,value)
            if k=='af' then
                h.writes=h.writes+1
                if h.fail then return false,'test failure' end
                h.filters=value; if h.observers['af'] then h.observers['af']('af',value) end
            else
                h.props[k]=value
            end
            return true
        end,
        set_property=function(k,v) h.props[k]=v end,
        del_property=function(k) h.props[k]=nil end,
        command_native=function(tbl)
            h.native_commands=h.native_commands or {}
            table.insert(h.native_commands,tbl)
            return true
        end,
        observe_property=function(k,t,fn) h.observers[k]=fn; if k=='af' then h.observer=fn end end,
        register_script_message=function(name,fn) h.messages[name]=fn end,
        register_event=function(name,fn) h.events=h.events or {}; h.events[name]=fn end,
        unregister_event=function(fn) h.unregistered=h.unregistered or {}; table.insert(h.unregistered,fn) end,
        add_key_binding=function() error('Mouse controls must not require a keyboard binding') end,
        add_periodic_timer=function(sec, fn)
            h.periodic_timers=h.periodic_timers or {}
            local t={sec=sec, fn=fn, dead=false}
            t.kill=function() t.dead=true end
            table.insert(h.periodic_timers, t)
            return t
        end,
        add_timeout=function(sec,fn)
            h.timeouts=h.timeouts or {}
            local t={sec=sec,fn=fn,dead=false}
            t.kill=function() t.dead=true end
            table.insert(h.timeouts,t)
            return t
        end,
        command_native_async=function(tbl,cb)
            h.async_commands=h.async_commands or {}
            table.insert(h.async_commands,{table=tbl,callback=cb})
            if h.async_handler then h.async_handler(tbl,cb) end
        end,
        command=function(...) h.last_command={...} end,
        commandv=function(...)
            h.arg_count=select('#',...)
            local c={...}
            if c[1]=='dump-cache' then
                h.last_dump_cache=c
                return true
            end
            if not h.ui_ready then error('uosc has not started yet') end
            eq(c[1],'script-message-to');eq(c[2],'uosc')
            if c[3]=='set-button' then
                h.buttons[c[4]]=c[5]
                if c[4]=='stable-volume' then h.button=c[5] end
                h.sends=h.sends+1
            elseif c[3]=='open-menu' then
                h.menu=c[4]
            end
        end,
        osd_message=function(text) h.osd=text end}
    package.loaded['mp.utils']=nil;package.loaded['mp.msg']=nil
    package.preload['mp.utils']=function() return {
        format_json=function(value) return value,nil end,
        parse_json=function(str) return (h.parse_json_fn and h.parse_json_fn(str)) or h.parsed_json or {} end,
        file_info=function(path) return h.file_info or {size=1048576} end,
        read_file=function(path) return h.file_content or '' end,
    } end
    package.preload['mp.msg']=function() return {info=function() end, warn=function() end, error=function() end, debug=function() end} end
    dofile('scripts/player-toolbar.lua')
    function h:click()
        local c=self.button.command;eq(c[1],'script-message-to');eq(c[2],'player_toolbar')
        self.messages[c[3]]()
    end
    return h
end
test('startup publishes a distinct inactive icon without changing audio',function()
    local h=harness();eq(h.writes,0);eq(h.button.icon,'graphic_eq');eq(h.button.active,false)
    eq(h.button.badge,nil);eq(h.button.tooltip,'Stable volume: Off')
end)
test('the icon command toggles audio without any physical key binding',function()
    local h=harness();h:click();eq(h.writes,1);eq(#h.filters,1);eq(h.filters[1].label,label)
    eq(h.filters[1].params.graph,graph);eq(h.button.active,true);eq(h.button.badge,nil)
end)
test('toggle preserves unrelated filters and removes only its preset',function()
    local own=filter('volume=0.5','user');local original={own};local h=harness(original)
    h:click();eq(#original,1);eq(h.filters[1],own);eq(#h.filters,2)
    h:click();eq(#h.filters,1);eq(h.filters[1],own);eq(h.button.active,false)
end)
test('the exact legacy F8 pair is recognized without double processing',function()
    local user=filter('volume=0.5','user');local h=harness({user,filter(normalizer),filter(limiter)})
    eq(h.button.active,true);h:click();eq(#h.filters,1);eq(h.filters[1],user)
    h:click();eq(#h.filters,2);eq(h.filters[2].label,label)
end)
test('user-labelled lookalike filters remain untouched',function()
    local a,b=filter(normalizer,'mine'),filter(limiter,'my-limit');local h=harness({a,b})
    eq(h.button.active,false);h:click();eq(#h.filters,3)
    h:click();eq(#h.filters,2);eq(h.filters[1],a);eq(h.filters[2],b)
end)
test('an unrelated filter using the reserved label is not overwritten',function()
    local collision=filter('volume=0.5',label);local h=harness({collision});h:click()
    eq(h.writes,0);eq(h.filters[1],collision);assert(h.osd:find('already in use',1,true))
end)
test('disabled owned preset is enabled without duplicating it',function()
    local h=harness({filter(graph,label,false)});eq(h.button.active,false)
    h:click();eq(#h.filters,1);eq(h.filters[1].enabled,true);eq(h.button.active,true)
end)
test('failed property writes never report a successful On state',function()
    local h=harness();h.fail=true;h:click();eq(#h.filters,0);eq(h.button.active,false)
    assert(h.osd:find("couldn't be changed",1,true))
end)
test('external changes update the icon state',function()
    local h=harness();h.filters={filter(graph,label)};h.observer('af',h.filters)
    eq(h.button.active,true);h.filters={};h.observer('af',h.filters);eq(h.button.active,false)
end)
test('unchanged state does not trigger redundant toolbar redraws',function()
    local h=harness();local before=h.sends
    for i=1,10 do h.observer('af',{}) end
    eq(h.sends,before)
end)
test('uosc startup or restart receives the current button state',function()
    local h=harness();local before=h.sends;h.messages['uosc-version']('5.13.0')
    eq(h.sends,before+4);h:click();h.messages['uosc-version']('5.13.0');eq(h.button.active,true)
end)
test('partially disabled legacy preset is replaced without duplicate filters',function()
    local old={filter(normalizer,nil,false),filter(limiter)};local h=harness(old)
    eq(h.button.active,false);h:click();eq(#h.filters,1);eq(h.filters[1].params.graph,graph)
    eq(#old,2);eq(old[1].enabled,false)
end)
test('uosc can start later without aborting the toolbar script',function()
    local h=harness({},true);eq(h.writes,0);eq(h.button,nil)
    eq(type(h.messages['toggle-stable-volume']),'function')
    h.ui_ready=true;h.messages['uosc-version']('5.13.0');eq(h.button.icon,'graphic_eq')
    h:click();eq(h.button.active,true)
end)
test('stream quality button publishes resolution badge and opens quality menu',function()
    local h=harness()
    eq(h.buttons['stream-quality'].icon,'settings')
    eq(h.buttons['stream-quality'].badge,nil)
    h.props['height']=1080
    h.observers['height']('height',1080)
    assert(h.buttons['stream-quality'].icon:find('HD',1,true))
    eq(h.buttons['stream-quality'].badge,nil)
    h.parsed_json={formats={
        {vcodec='avc1',height=1080,fps=60},
        {vcodec='avc1',height=720,fps=30},
        {vcodec='avc1',height=480},
    }}
    h.props['user-data/mpv/ytdl/json-subprocess-result']={status=0,stdout='fixture'}
    h.messages['open-quality-menu']()
    assert(h.menu~=nil)
    eq(h.menu.type,'stream_quality_menu')
    -- 2-action submenus per resolution row + 'Default: any resolution'
    -- (no saved default → no 'Apply default now' entry; the old standalone
    -- 'Save playing quality as default' row is gone — the submenu covers it).
    eq(#h.menu.items,4)
    eq(h.menu.items[1].title,'1080p60')
    eq(h.menu.items[1].active,true)
    eq(h.menu.items[1].hint,'Current')
    eq(h.menu.items[1].items[1].title,'Set as default')
    eq(h.menu.items[1].items[1].hint,'this + future streams')
    eq(h.menu.items[1].items[1].value[4],'1080')
    eq(h.menu.items[1].items[2].title,'Just this video')
    eq(h.menu.items[1].items[2].value[5],'1080p60')
    eq(h.menu.items[2].title,'720p')
    eq(h.menu.items[2].active,false)
    eq(h.menu.items[4].title,'Default: any resolution')
    -- Display larger than the source → the OSD spells the rescale out, so
    -- stats-for-nerds' window-size line can't be mistaken for stream quality.
    h.props['osd-width']=1920; h.props['osd-height']=1080
    h.messages['set-quality']('720')
    -- Same formula as the saved default (stream_policy.stream_default_format):
    -- the height cap plus the muxed-best fallback tail.
    eq(h.props['ytdl-format'],'bestvideo[height<=?720]+bestaudio/best[height<=?720]/best')
    assert(h.osd:find('upscale: 1920x1080 display',1,true), 'upscale note missing')
    -- matching display → no note at all
    h.props['osd-width']=1280; h.props['osd-height']=720
    h.messages['set-quality']('720')
    assert(h.osd=='Quality: 720p', 'unexpected display note: '..tostring(h.osd))
end)

-- sandbox for persisted-default tests (os.execute is unavailable inside mpv,
-- so conf files are written straight into TEMP instead of a subdirectory)
local function sandbox_conf(seed_default)
    local path=(os.getenv('TEMP') or '.')..'\\stream_quality_conf_'
        ..tostring(os.time())..'_'..tostring(math.random(100000))..'.conf'
    if seed_default then
        local f=assert(io.open(path,'w'))
        f:write('shipped comment line\n')
        f:write('default_quality='..tostring(seed_default)..'\n')
        f:close()
    end
    return path
end
test('quality menu marks the saved default and offers persistence actions',function()
    local path=sandbox_conf(720)
    local h=harness(nil,nil,{conf_path=path})
    h.props['height']=1080
    h.parsed_json={formats={
        {vcodec='avc1',height=1080,fps=60},
        {vcodec='avc1',height=720,fps=30},
        {vcodec='avc1',height=480},
    }}
    h.props['user-data/mpv/ytdl/json-subprocess-result']={status=0,stdout='fixture'}
    h.messages['open-quality-menu']()
    -- 3 resolution rows (with submenus) + 'Apply default now' + 'Default: any resolution'
    eq(#h.menu.items,5)
    -- item identity first: heights present in the json-subprocess fixture,
    -- reachable via each row's 'Set as default' submenu action
    eq(h.menu.items[1].items[1].value[4],'1080')
    eq(h.menu.items[2].items[1].value[4],'720')
    eq(h.menu.items[3].items[1].value[4],'480')
    eq(h.menu.items[1].hint,'Current')
    eq(h.menu.items[2].hint,'Default')
    eq(h.menu.items[4].title,'Apply default now')
    eq(h.menu.items[4].hint,'720p')
    eq(h.menu.items[5].title,'Default: any resolution')
    os.remove(path)
end)
test('set-default persists straight from the submenu row and re-drives playback',function()
    local path=sandbox_conf()
    local h=harness(nil,nil,{conf_path=path})
    h.props['duration']=100; h.props['time-pos']=12
    h.messages['set-default']('720','720p')
    local f=io.open(path,'r'); assert(f, 'conf file was not created'); local content=f:read('*a'); f:close()
    assert(content:find('default_quality=720',1,true), 'saved value missing')
    -- 'Set as default' also re-drives the playing stream from the saved conf
    eq(h.props['ytdl-format'],'')
    assert(h.events['file-loaded']~=nil)
    assert(h.osd:find('future streams',1,true))
    os.remove(path)
end)
-- ─── fast quality switch (reuses signed URLs, no re-extraction) ───────
local function stream_fixture()
    return {formats={
        {height=1080,vcodec='avc1',fps=60,protocol='https',url='https://media.example/v1080',tbr=4000},
        {height=1080,vcodec='avc1',fps=30,protocol='https',url='https://media.example/v1080-30',tbr=2500},
        {height=720,vcodec='avc1',fps=30,protocol='https',url='https://media.example/v720',tbr=1000},
        {height=480,vcodec='avc1',fps=30,protocol='https',url='https://media.example/v480',tbr=600},
        {vcodec='none',acodec='opus',protocol='https',url='https://media.example/a-lo',abr=64},
        {vcodec='none',acodec='opus',protocol='https',url='https://media.example/a-hi',abr=256},
    },http_headers={['User-Agent']='ua-json'}}
end
test('set-quality reuses signed URLs instead of re-extracting',function()
    local path=sandbox_conf()
    local h=harness(nil,nil,{conf_path=path})
    h.props['height']=1080; h.props['duration']=200; h.props['time-pos']=17
    h.parsed_json=stream_fixture()
    h.props['user-data/mpv/ytdl/json-subprocess-result']={status=0,stdout='fixture'}
    h.messages['set-quality']('720','720p')
    -- fast path: pre-resolved marker + direct loadfile with the best audio
    -- as a secondary track; the playlist replay never runs
    eq(h.props['user-data/mpv/ytdl/fast-url'],'https://media.example/v720')
    eq(#h.native_commands,1)
    local c=h.native_commands[1]
    eq(c[1],'loadfile'); eq(c[2],'https://media.example/v720')
    eq(c[3],'replace'); eq(c[4],-1)
    eq(c[5]['audio-file'],'https://media.example/a-hi')
    eq(c[5]['user-agent'],'ua-json')
    eq(h.last_command,nil)
    -- clicking the playing resolution is a no-op, not a second load
    local before=#h.native_commands
    h.messages['set-quality']('1080','1080p60')
    eq(#h.native_commands,before)
    assert(h.osd:find('already',1,true))
    -- ...but a higher-fps row at the same height still switches
    h.props['container-fps']=30
    h.messages['set-quality']('1080','1080p60')
    eq(#h.native_commands,before+1)
    eq(h.native_commands[#h.native_commands][2],'https://media.example/v1080')
    os.remove(path)
end)
test('muxed rows switch as a single file without a secondary audio track',function()
    local path=sandbox_conf()
    local h=harness(nil,nil,{conf_path=path})
    h.props['height']=480; h.props['duration']=50; h.props['time-pos']=3
    h.parsed_json={formats={
        {height=720,vcodec='avc1',acodec='mp4a.40.2',protocol='https',url='https://media.example/mux720',tbr=800},
        {height=1080,vcodec='avc1',fps=30,protocol='https',url='https://media.example/v1080',tbr=4000},
        {vcodec='none',acodec='opus',protocol='https',url='https://media.example/a-hi',abr=256},
    }}
    h.props['user-data/mpv/ytdl/json-subprocess-result']={status=0,stdout='fixture'}
    h.messages['set-quality']('720','720p')
    eq(h.props['user-data/mpv/ytdl/fast-url'],'https://media.example/mux720')
    local c=h.native_commands[#h.native_commands]
    eq(c[5]['audio-file'],nil)  -- muxed row carries its own audio
    os.remove(path)
end)
test('apply-default fast path picks the best row at or below the ceiling',function()
    local path=sandbox_conf(720)
    local h=harness(nil,nil,{conf_path=path})
    h.props['height']=1080; h.props['duration']=10; h.props['time-pos']=1
    h.parsed_json=stream_fixture()
    h.props['user-data/mpv/ytdl/json-subprocess-result']={status=0,stdout='fixture'}
    h.messages['apply-default']()
    eq(h.props['ytdl-format'],'')  -- session override dropped before the load
    eq(h.props['user-data/mpv/ytdl/fast-url'],'https://media.example/v720')
    local c=h.native_commands[#h.native_commands]
    eq(c[5]['audio-file'],'https://media.example/a-hi')
    assert(h.osd:find('default (720p)',1,true))
    eq(#h.timeouts,1)  -- heal watcher armed for the fast load
    os.remove(path)
end)
test('default-off fast path picks the top available row',function()
    local path=sandbox_conf(720)
    local h=harness(nil,nil,{conf_path=path})
    h.props['duration']=10; h.props['time-pos']=1
    h.parsed_json=stream_fixture()
    h.props['user-data/mpv/ytdl/json-subprocess-result']={status=0,stdout='fixture'}
    h.messages['default-off']()
    eq(h.props['user-data/mpv/ytdl/fast-url'],'https://media.example/v1080')
    local c=h.native_commands[#h.native_commands]
    eq(c[5]['audio-file'],'https://media.example/a-hi')
    local f=io.open(path,'r'); local content=f:read('*a'); f:close()
    assert(content:find('default_quality=0',1,true))
    os.remove(path)
end)
test('fragmented rows fall back to the full reload pipeline',function()
    local path=sandbox_conf()
    local h=harness(nil,nil,{conf_path=path})
    h.props['height']=480; h.props['duration']=10; h.props['time-pos']=1
    h.parsed_json={formats={
        {height=720,vcodec='avc1',fps=30,protocol='m3u8_native',url='https://media.example/hls720',tbr=1000},
        {vcodec='none',acodec='opus',protocol='m3u8_native',url='https://media.example/hls-a',abr=128},
    }}
    h.props['user-data/mpv/ytdl/json-subprocess-result']={status=0,stdout='fixture'}
    h.messages['set-quality']('720','720p')
    eq(h.props['user-data/mpv/ytdl/fast-url'],nil)
    assert(h.last_command[1]:find('playlist-play-index',1,true))
    eq(h.props['ytdl-format'],'bestvideo[height<=?720]+bestaudio/best[height<=?720]/best')
    os.remove(path)
end)
test('current resolution matches the default when saved as such',function()
    local path=sandbox_conf(1080)
    local h=harness(nil,nil,{conf_path=path})
    h.props['height']=1080
    h.parsed_json={formats={{vcodec='avc1',height=1080,fps=60}}}
    h.props['user-data/mpv/ytdl/json-subprocess-result']={status=0,stdout='fixture'}
    h.messages['open-quality-menu']()
    eq(#h.menu.items,3)
    eq(h.menu.items[1].hint,'Current · Default')
    os.remove(path)
end)
test('save-default persists the playing height and drops the session override',function()
    local path=sandbox_conf()
    local h=harness(nil,nil,{conf_path=path})
    h.props['height']=1080; h.props['duration']=100; h.props['time-pos']=42
    h.messages['save-default']()
    local f=io.open(path,'r'); assert(f, 'conf file was not created'); local content=f:read('*a'); f:close()
    assert(content:find('default_quality=1080',1,true), 'saved value missing')
    assert(content:find('ceiling',1,true), 'shipped header comment preserved')
    eq(h.props['ytdl-format'],'')
    assert(h.events['file-loaded']~=nil)
    assert(h.osd:find('1080',1,true))
    os.remove(path)
end)
test('default-off removes the cap without touching style comments',function()
    local path=sandbox_conf(480)
    local h=harness(nil,nil,{conf_path=path})
    h.messages['default-off']()
    local f=io.open(path,'r'); local content=f:read('*a'); f:close()
    assert(content:find('default_quality=0',1,true))
    assert(content:find('shipped comment line',1,true))
    assert(h.osd:find('any resolution',1,true))
    os.remove(path)
end)
test('save-default with no video only explains itself',function()
    local path=sandbox_conf()
    local h=harness(nil,nil,{conf_path=path})
    h.messages['save-default']()
    assert(h.osd:find('play a video first',1,true))
    eq(io.open(path,'r'),nil)
    os.remove(path)
end)
test('apply-default clears the override and re-resolves from the conf',function()
    local path=sandbox_conf(480)
    local h=harness(nil,nil,{conf_path=path})
    h.props['ytdl-format']='bestvideo[height<=?2160]+bestaudio/best[height<=?2160]'
    h.props['height']=480; h.props['duration']=100; h.props['time-pos']=7
    h.messages['apply-default']()
    eq(h.props['ytdl-format'],'')
    assert(h.osd:find('default',1,true))
    os.remove(path)
end)
test('audio tracks button publishes language badge and opens clean deduplicated audio menu',function()
    local h=harness()
    assert(h.buttons['audio-tracks']~=nil)
    eq(h.buttons['audio-tracks'].icon,'headphones')
    eq(h.buttons['audio-tracks'].badge,nil)
    -- Include duplicate bitrate variants of Arabic to test deduplication
    h.props['track-list']={
        {type='audio',id=1,lang='ar',title='Arabic',selected=false,['demux-bitrate']=48000},
        {type='audio',id=2,lang='ar',title='Arabic',selected=true,['demux-bitrate']=128000},
        {type='audio',id=3,lang='ar',title='Arabic',selected=false,['demux-bitrate']=64000},
        {type='audio',id=4,lang='ja',title='Japanese',selected=false,['demux-bitrate']=128000},
    }
    h.props['current-tracks/audio/id']=2
    h.observers['track-list']('track-list',h.props['track-list'])
    assert(h.buttons['audio-tracks'].icon:find('AR',1,true))
    eq(h.buttons['audio-tracks'].badge,nil)
    eq(h.buttons['audio-tracks'].tooltip,'Audio: Arabic')

    h.messages['open-audio-menu']()
    assert(h.menu~=nil)
    eq(h.menu.type,'audio_tracks_menu')
    -- Exactly 2 deduplicated items instead of 4
    eq(#h.menu.items,2)
    eq(h.menu.items[1].title,'Arabic')
    eq(h.menu.items[1].active,true)
    eq(h.menu.items[1].hint,'Current')
    eq(h.menu.items[1].value[3],'2')
    eq(h.menu.items[2].title,'Japanese')
    eq(h.menu.items[2].active,false)
    eq(h.menu.items[2].hint,nil)
    eq(h.menu.items[2].value[2],'aid')
    eq(h.menu.items[2].value[3],'4')

    h.props['track-list'][2].selected=false
    h.props['track-list'][4].selected=true
    h.props['current-tracks/audio/id']=4
    h.observers['track-list']('track-list',h.props['track-list'])
    assert(h.buttons['audio-tracks'].icon:find('JA',1,true))
    eq(h.buttons['audio-tracks'].badge,nil)
    eq(h.buttons['audio-tracks'].tooltip,'Audio: Japanese')
end)
test('JSON secondary returns never become extra command arguments',function()
    local h=harness();eq(h.arg_count,5);h:click();eq(h.arg_count,5)
    h:click();eq(h.arg_count,5);eq(h.button.badge,nil)
end)
test('download button publishes idle state and runs background subprocess on click',function()
    local h=harness()
    local btn=h.buttons['download-video']
    assert(btn~=nil)
    eq(btn.icon,'file_download')
    eq(btn.active,false)
    eq(btn.badge,nil)
    eq(btn.tooltip,'Download video')
    eq(#(h.timeouts or {}),0)

    -- Missing online stream URL
    h.messages['start-download']()
    assert(h.osd:find('Download only works for online streams/URLs',1,true))

    -- Set active stream path
    h.props['path']='https://www.youtube.com/watch?v=mock'
    h.props['media-title']='Mock YouTube Video'
    local captured_args,captured_cb
    h.async_handler=function(tbl,cb)
        captured_args=tbl.args
        captured_cb=cb
    end

    h.messages['start-download']()
    eq(h.buttons['download-video'].active,true)
    eq(h.buttons['download-video'].badge,'DL')
    assert(h.osd:find('Starting Video download: Mock YouTube Video',1,true))
    assert(captured_args~=nil)
    if captured_args[1] == 'python' then
        assert(captured_args[2]:find('download_worker.py', 1, true) ~= nil)
    else
        eq(captured_args[1], 'yt-dlp')
    end

    -- Second click while downloading warns user
    h.messages['start-download']()
    assert(h.osd:find('already in progress',1,true))

    -- Complete download successfully
    captured_cb(true,{status=0},nil)
    eq(h.buttons['download-video'].active,false)
    eq(h.buttons['download-video'].badge,'OK')
    assert(h.osd:find('Download complete: Mock YouTube Video',1,true))
    eq(#(h.timeouts or {}),1)
    -- Trigger timeout to clear OK badge
    h.timeouts[1].fn()
    eq(h.buttons['download-video'].badge,nil)
end)
test('download button extracts URL when source-url has JSON quotes or edl stream path',function()
    local h=harness()
    h.props['user-data/mpv/ytdl/source-url'] = '"https://txxx.com/videos/17007267/mock/"'
    h.props['media-title'] = 'Non-YouTube Video'
    local captured_args
    h.async_handler = function(tbl, cb)
        captured_args = tbl.args
    end
    h.messages['start-download']()
    assert(captured_args ~= nil)
    eq(captured_args[#captured_args], 'https://txxx.com/videos/17007267/mock/')
end)
test('download button dumps cache directly when video is completely buffered', function()
    local h=harness()
    h.props['path']='https://www.youtube.com/watch?v=buffered_video'
    h.props['media-title']='Cached Video Title'
    h.props['duration']=120
    h.props['demuxer-cache-state']={
        bof=true,
        eof=true,
        ['seekable-ranges']={{start=0, ['end']=120}}
    }
    h.file_info={size=50000000}
    h.messages['start-download']()
    assert(h.last_dump_cache~=nil)
    eq(h.last_dump_cache[1], 'dump-cache')
    eq(h.last_dump_cache[2], '0')
    eq(h.last_dump_cache[3], '120')
    assert(h.last_dump_cache[4]:find('Cached Video Title.mp4') ~= nil)
    eq(h.buttons['download-video'].badge, 'SAVED')
    assert(h.osd:find('Saved from cache: Cached Video Title', 1, true))
    eq(#(h.timeouts or {}), 1)
    h.timeouts[1].fn()
    eq(h.buttons['download-video'].badge, nil)
end)
test('download button retries with secondary stream URL on primary failure and formats error', function()
    local h=harness()
    h.props['user-data/mpv/ytdl/source-url'] = '""https://site.com/watch/123""'
    h.props['path'] = 'edl://!new_stream;%32%https://cdn.site.com/direct.mp4,length=100'
    h.props['media-title'] = 'Test Stream'

    local calls = {}
    h.async_handler = function(tbl, cb)
        table.insert(calls, {args=tbl.args, cb=cb})
    end

    h.messages['start-download']()
    eq(#calls, 1)
    eq(calls[1].args[#calls[1].args], 'https://site.com/watch/123')

    -- Simulate primary failure with yt-dlp error
    calls[1].cb(false, {status=1, stderr='ERROR: [site] HTTP Error 403: Forbidden'}, nil)

    -- Should automatically retry with secondary URL!
    eq(#calls, 2)
    eq(calls[2].args[#calls[2].args], 'https://cdn.site.com/direct.mp4')

    -- Simulate secondary failure with error message
    calls[2].cb(false, {status=1, stderr='ERROR: [generic] HTTP Error 404: Not Found'}, nil)
    eq(h.buttons['download-video'].badge, 'ERR')
    assert(h.osd:find('Download error: HTTP Error 404: Not Found', 1, true) ~= nil)
end)
test('download button polls status file and updates progress badge and tooltip', function()
    local h=harness()
    h.props['user-data/mpv/ytdl/source-url'] = 'https://site.com/video/123'
    h.props['media-title'] = 'Progress Test Video'

    local async_cb
    h.async_handler = function(tbl, cb)
        async_cb = cb
    end

    h.file_content = '{"status": "downloading", "percent": 45.2, "percent_int": 45, "speed": "12.5MiB/s", "eta": "00:08", "threads": 16}'
    h.parse_json_fn = function(str)
        return {status="downloading", percent=45.2, percent_int=45, speed="12.5MiB/s", eta="00:08", threads=16}
    end

    h.messages['start-download']()
    eq(#(h.periodic_timers or {}), 1)

    -- Trigger periodic poll
    h.periodic_timers[1].fn()
    eq(h.buttons['download-video'].badge, '45%')
    assert(math.abs((h.buttons['download-video'].progress or 0) - 0.452) < 0.001)
    assert(h.buttons['download-video'].tooltip:find('45%%') ~= nil)
    assert(h.buttons['download-video'].tooltip:find('12.5MiB/s') ~= nil)

    -- Trigger completion
    async_cb(true, {status=0}, nil)
    eq(h.buttons['download-video'].badge, 'OK')
    eq(h.buttons['download-video'].progress, 1.0)
    assert(h.buttons['download-video'].tooltip:find('complete') ~= nil)
    eq(h.periodic_timers[1].dead, true)
end)
print('Toolbar tests passed: '..total)
