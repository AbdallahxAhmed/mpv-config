local total=0
local function eq(a,b) assert(a==b,tostring(a)..' ~= '..tostring(b)) end
local function test(name,fn) fn(); total=total+1; print('ok paste: '..name) end
local function harness(clip, existing)
    local h={props={['clipboard/text']=clip},bindings={},events={},loads={}}
    local function get(k,d) local v=h.props[k]; if v==nil then return d end; return v end
    mp={msg={info=function() end,warn=function() end},get_time=function() return 0 end,
        get_property=get,get_property_native=get,get_property_bool=get,get_property_number=get,
        set_property=function(k,v) h.props[k]=v end,
        commandv=function(...) local c={...}; if c[1]=='loadfile' then h.loads[#h.loads+1]=c end end,
        osd_message=function(text) h.osd=text end,
        add_hook=function(_,priority,fn) h.hook={priority=priority,fn=fn} end,
        register_event=function(k,fn) h.events[k]=fn end,
        add_key_binding=function(_,k,fn) h.bindings[k]=fn end,
        add_periodic_timer=function(interval,fn)
            local timer={interval=interval,callback=fn,kill=function(self) self.killed=true end}
            h.timer=timer; return timer
        end}
    package.loaded['mp.utils']=nil
    package.preload['mp.utils']=function() return {file_info=function(path)
        if existing and existing[path] then return {is_file=true} end
    end} end
    dofile('scripts/smart-paste.lua')
    return h
end
test('quoted and partial YouTube links normalize',function()
    for _,v in ipairs({{'  "youtu.be/abc"  ','https://youtu.be/abc'},
        {'watch?v=abc&list=x','https://www.youtube.com/watch?v=abc&list=x'},
        {'shorts/abc','https://www.youtube.com/shorts/abc'},
        {'m.youtube.com/watch?v=x','https://www.youtube.com/watch?v=x'}}) do
        local h=harness(v[1]); h.bindings['paste-to-open'](); eq(h.loads[1][2],v[2]); eq(h.loads[1][3],'replace')
    end
end)
test('full URLs and mpv protocols are unchanged',function()
    for _,url in ipairs({'https://youtube.com.evil.test/a','ytdl://https://youtu.be/abc','https://youtu.be/abc'}) do
        local h=harness(url); h.bindings['paste-to-open'](); eq(h.loads[1][2],url)
    end
end)
test('local paths with URL-looking names remain local',function()
    for _,path in ipairs({'/media/youtube.com/shorts/a.mkv','C:\\media\\watch?v=abc.mkv',
        './shorts/a.mp4','~/watch?v=a','//server/share/youtube.com/a.mkv'}) do
        local h=harness(path); h.bindings['paste-to-open'](); eq(h.loads[1][2],path)
    end
end)
test('existing relative files take priority over URL fragments',function()
    local h=harness('shorts/local.mkv',{['shorts/local.mkv']=true})
    h.bindings['paste-to-open'](); eq(h.loads[1][2],'shorts/local.mkv')
end)
test('invalid clipboard types do not load or start timers',function()
    for _,value in ipairs({17,true,{}, {text=17},' '}) do
        local h=harness(value); h.bindings['paste-to-open'](); eq(#h.loads,0); eq(h.timer,nil)
    end
    local h=harness(nil); h.bindings['paste-to-open'](); eq(#h.loads,0)
end)
test('native clipboard string and table fallback work',function()
    for _,value in ipairs({'https://youtu.be/abc',{text='https://youtu.be/abc'}}) do
        local h=harness(nil); h.props.clipboard=value; h.bindings['paste-to-open']()
        eq(h.loads[1][2],'https://youtu.be/abc')
    end
end)
test('normalization precedes extractor and spinner is four Hz',function()
    local h=harness(nil); eq(h.hook.priority,5)
    h.props['stream-open-filename']='youtu.be/abc'; h.hook.fn()
    eq(h.props['stream-open-filename'],'https://youtu.be/abc'); eq(h.timer.interval,0.25); eq(#h.loads,0)
end)
test('repeated paste is deduplicated until load completes',function()
    local h=harness('https://youtu.be/abc'); h.bindings['paste-to-open'](); h.bindings['paste-to-open']()
    eq(#h.loads,1); h.events['file-loaded'](); assert(h.timer.killed)
    h.bindings['paste-to-open'](); eq(#h.loads,2)
end)
test('end-file kills spinner and local hook starts none',function()
    local h=harness('https://youtu.be/abc'); h.bindings['paste-to-open']()
    h.events['end-file']({reason='error'}); assert(h.timer.killed); assert(h.osd:find('Failed',1,true))
    h=harness(nil); h.props['stream-open-filename']='/media/local.mkv'; h.hook.fn(); eq(h.timer,nil)
end)
test('playlist paste appends without disturbing current playback',function()
    local h=harness('https://youtu.be/abc'); h.props['playlist-count']=2; h.props['idle-active']=false
    h.bindings['paste-to-playlist'](); eq(h.loads[1][3],'append'); eq(h.timer,nil)
    h=harness('https://youtu.be/abc'); h.props['idle-active']=true
    h.bindings['paste-to-playlist'](); eq(h.loads[1][3],'replace')
end)
print('Paste tests passed: '..total)
