-- Real Lua at the mpv boundary: click commands, state, and filter ownership.
local total = 0
local function eq(a,b) assert(a == b, tostring(a)..' ~= '..tostring(b)) end
local function test(name,fn) fn(); total=total+1; print('ok toolbar: '..name) end
local label = 'mpv_config_stable_volume'
local normalizer = 'dynaudnorm=f=500:g=15:p=0.95:m=10'
local limiter = 'alimiter=limit=0.9:level=false'
local graph = normalizer..','..limiter
local function filter(g,l,enabled) return {name='lavfi',label=l,enabled=enabled,params={graph=g}} end
local function harness(filters, no_ui)
    local h={filters=filters or {},messages={},writes=0,sends=0,ui_ready=not no_ui,buttons={},props={},observers={}}
    mp={log=function() end,get_script_name=function() return 'player_toolbar' end,
        get_property_native=function(k,d) if k=='af' then return h.filters end; return h.props[k] or d end,
        get_property_number=function(k,d) return tonumber(h.props[k]) or d end,
        get_property=function(k,d) return h.props[k] or d end,
        set_property_native=function(k,value)
            eq(k,'af'); h.writes=h.writes+1
            if h.fail then return false,'test failure' end
            h.filters=value; if h.observers['af'] then h.observers['af']('af',value) end; return true
        end,
        set_property=function(k,v) h.props[k]=v end,
        observe_property=function(k,t,fn) h.observers[k]=fn; if k=='af' then h.observer=fn end end,
        register_script_message=function(name,fn) h.messages[name]=fn end,
        register_event=function(name,fn) h.events=h.events or {}; h.events[name]=fn end,
        add_key_binding=function() error('Mouse controls must not require a keyboard binding') end,
        add_periodic_timer=function() error('Toolbar must not poll') end,
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
            if not h.ui_ready then error('uosc has not started yet') end
            local c={...}
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
        parse_json=function(str) return h.parsed_json or {} end,
    } end
    package.preload['mp.msg']=function() return {warn=function() end} end
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
    eq(#h.menu.items,3)
    eq(h.menu.items[1].title,'1080p60')
    eq(h.menu.items[1].active,true)
    eq(h.menu.items[1].hint,'Current')
    eq(h.menu.items[2].title,'720p')
    eq(h.menu.items[2].active,false)
    h.messages['set-quality']('720')
    eq(h.props['ytdl-format'],'bestvideo[height<=?720]+bestaudio/best[height<=?720]')
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
    eq(captured_args[1],'yt-dlp')

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
print('Toolbar tests passed: '..total)
