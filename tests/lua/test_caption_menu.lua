-- Real Lua, mocked mpv boundary: no player, network, shell or filesystem writes.
local count = 0
local function eq(a,b) assert(a == b, tostring(a)..' ~= '..tostring(b)) end
local function test(name, fn) fn(); count=count+1; print('ok captions: '..name) end
local data = {subtitles={en={{ext='vtt',name='English',url='https://captions.example/manual.vtt'}}},
    automatic_captions={ar={{ext='vtt',name='Arabic',url='https://captions.example/ar.vtt'}},
    fr={{ext='vtt',name='French',url='https://captions.example/auto?tlang=fr'}}}}
local function harness(metadata)
    local h = {props={path='https://youtu.be/test-video',sid=false,['sub-visibility']=false,
        ['track-list']={},slang={'ar','en'},['options/ytdl-raw-options']={},
        ['user-data/mpv/ytdl/path']='yt-dlp'}, commands={}, events={}, messages={}, jobs={}, timers={}, aborted={}, parses=0}
    h.props['user-data/mpv/ytdl/json-subprocess-result']={status=0,stdout='cached'}
    h.metadata = metadata or data
    local function get(k, default) local v=h.props[k]; if v == nil then return default end; return v end
    local log = setmetatable({}, {__index=function() return function() end end})
    mp = {log=function() end, msg=log, get_script_name=function() return 'ytdl_sub_menu' end,
        find_config_file=function(name) return name end, get_opt=function() end,
        get_property=get, get_property_native=get, get_property_bool=get,
        set_property=function(k,v) h.props[k]=v end, set_property_bool=function(k,v) h.props[k]=v end,
        register_event=function(k,fn) h.events[k]=fn end,
        register_script_message=function(k,fn) h.messages[k]=fn end,
        add_key_binding=function(_,k,fn) h.messages['binding:'..k]=fn end,
        osd_message=function(text) h.osd=text end,
        commandv=function(...) local c={...}; h.commands[#h.commands+1]=c; if c[3]=='open-menu' then eq(select('#',...),4); h.menu=c[4] end end,
        command_native_async=function(command,cb) local id=#h.jobs+1; h.jobs[id]={command=command,callback=cb}; return id end,
        observe_property=function(name,type,fn) h.observers=h.observers or {}; h.observers[name]=fn end,
        unobserve_property=function(fn) end,
        abort_async_command=function(id) h.aborted[id]=true end,
        add_timeout=function(_,cb) local t={callback=cb,kill=function(self) self.killed=true end}; h.timers[#h.timers+1]=t; return t end}
    package.loaded['mp.utils']=nil; package.loaded['mp.msg']=nil; package.loaded['mp.options']=nil
    package.preload['mp.utils']=function() return {file_info=function() end,
        format_json=function(v) return v,nil end, parse_json=function(text) h.parses=h.parses+1; if text=='bad' then return nil end; return h.metadata end} end
    package.preload['mp.msg']=function() return log end
    package.preload['mp.options']=function() return {read_options=function() end} end
    dofile('scripts/ytdl-sub-menu.lua')
    function h:load() self.events['start-file'](); self.events['file-loaded']() end
    function h:open() self.messages.open(); return self.menu end
    function h:activate(item) local v=item.value; assert(type(v)=='table'); self.messages[v[3]](table.unpack(v,4)) end
    function h:caption(kind) local m=self:open(); for _,v in ipairs(m.items) do if v.title==kind then return v.items[1] end end; error('missing '..kind) end
    function h:quote_user_data_strings()
        mp.get_property=function(k,default)
            local value=get(k,default)
            if k:match('^user%-data/') and type(value)=='string' then return '"'..value..'"' end
            return value
        end
    end
    return h
end
test('zero startup requests and no metadata parse until menu opens',function()
    local h=harness(); h:load(); eq(#h.jobs,0); eq(h.parses,0); eq(#h.timers,0)
    h:open(); eq(h.parses,1); eq(#h.jobs,0); h:open(); eq(h.parses,1)
end)
test('separate creator generated and translated menus',function()
    local h=harness(); h:load()
    assert(h:caption('Creator captions')); assert(h:caption('Auto-generated')); assert(h:caption('Auto-translated'))
    eq(#h.jobs,0)
end)
test('one cancellable async curl fetch and sub-add, no extractor and no reload',function()
    local h=harness(); h:load(); local item=h:caption('Auto-generated'); h:activate(item)
    eq(#h.jobs,1); local c=h.jobs[1].command
    eq(c.name,'subprocess')
    assert(c.args[1]:find('curl'))
    assert(c.args[#c.args]:find('%.vtt$'))
    h:activate(item); eq(#h.jobs,1)
    h.jobs[1].callback(true,{status=0}); eq(h.props['sub-visibility'],true); assert(h.timers[1].killed)
    local sub_add_cmd = h.commands[#h.commands]
    eq(sub_add_cmd[1],'sub-add')
    assert(sub_add_cmd[2]:find('%.vtt$'))
    eq(sub_add_cmd[3],'select')
    eq(sub_add_cmd[5],'ar')
    for _,v in ipairs(h.commands) do assert(v[1]~='loadfile' and v[1]~='run') end
end)
test('re-selecting a loaded caption does not download it again',function()
    local h=harness(); h:load(); h.props['track-list']={{type='sub',id=7,['external-filename']='https://captions.example/ar.vtt'}}
    h.messages['fetch-sub']('ar'); eq(#h.jobs,0); eq(h.props.sid,'7'); eq(h.props['sub-visibility'],true)
end)
test('switching files aborts request and invalidates old menu actions',function()
    local h=harness(); h:load(); local old=h:caption('Auto-generated'); h:activate(old)
    h.events['end-file'](); h.props.path='https://youtu.be/next'; h:load()
    assert(h.aborted[1]); assert(h.timers[1].killed)
    h.jobs[1].callback(true,{}); eq(h.props['sub-visibility'],false)
    h:activate(old); eq(#h.jobs,1)
end)
test('Off cancels an in-flight caption load',function()
    local h=harness(); h:load(); local m=h:open(); local off=m.items[1]
    h.messages['fetch-sub']('ar'); h:activate(off); assert(h.aborted[1]); eq(h.props.sid,'no')
    h.jobs[1].callback(true,{}); eq(h.props['sub-visibility'],false)
end)
test('timeout aborts and remains retryable',function()
    local h=harness(); h:load(); h.messages['fetch-sub']('ar')
    h.timers[1].callback(); assert(h.aborted[1]); assert(h.osd:find('timed out',1,true))
    h.messages['fetch-sub']('ar'); eq(#h.jobs,2)
end)
test('nil failed subprocess results are handled',function()
    local h=harness({}); h:load(); h.messages['fetch-sub']('ar'); eq(h.jobs[1].command.name,'subprocess')
    h.jobs[1].callback(false,nil,'error'); assert(h.osd:find('Could not refresh',1,true))
    h.messages['fetch-sub']('ar'); eq(#h.jobs,2)
end)
test('refresh is explicit deduplicated and does not inherit exec/output flags',function()
    local h=harness({}); h:load(); h.props['options/ytdl-raw-options']={exec='UNSAFE',output='/tmp/wrong',proxy='http://proxy.example:8080'}
    h:open(); eq(#h.jobs,0); h.messages['fetch-sub']('ar'); h.messages['fetch-sub']('ar'); eq(#h.jobs,1)
    local args=h.jobs[1].command.args; local found={}; for _,v in ipairs(args) do found[v]=true end
    assert(found['--ignore-config']); assert(found['--proxy']); assert(not found['--exec']); assert(not found['--output'])
    eq(args[#args-1],'--'); eq(args[#args],h.props.path)
end)
test('local files and fake YouTube hosts retain the standard menu',function()
    local h=harness(); h:load()
    for _,p in ipairs({'/media/local.mkv','https://youtube.com.evil.test/a'}) do
        h.props.path=p; h:open(); local c=h.commands[#h.commands]; eq(c[1],'script-binding'); eq(c[2],'uosc/subtitles')
    end
    eq(h.parses,0); eq(#h.jobs,0)
end)
test('malicious titles never become command text',function()
    local h=harness({subtitles={en={{ext='vtt',name='"; run bad; #',url='https://captions.example/safe'}}}})
    h:load(); local v=h:caption('Creator captions').value
    eq(v[1],'script-message-to'); eq(v[3],'select-caption'); assert(v[4]:match('^%d+:%d+:%d+$'))
    h.messages['fetch-sub']('en;run bad'); eq(#h.jobs,0)
end)
test('shared source URL is read as a native node value',function()
    local h=harness(); h:load(); h:quote_user_data_strings()
    h.props.path='/media/local-fixture.ppm'
    h.props['user-data/mpv/ytdl/source-url']='https://youtu.be/fixture'
    h.messages['fetch-sub']('ar'); eq(#h.jobs,1); eq(h.jobs[1].command.name,'subprocess')
    assert(h.jobs[1].command.args[1]:find('curl'))
end)
test('shared downloader path is not JSON-quoted when spawning',function()
    local h=harness({}); h:load(); h:quote_user_data_strings()
    h.props['user-data/mpv/ytdl/path']='/tmp/tools with spaces/yt-dlp'
    h.messages['fetch-sub']('ar')
    eq(h.jobs[1].command.args[1],'/tmp/tools with spaces/yt-dlp')
end)
test('the toolbar action opens captions with one JSON argument and no keypress',function()
    local h=harness(); h:load(); h.messages['binding:open']()
    eq(h.menu.type,'ytdl_sub_menu'); eq(#h.jobs,0)
    for _,command in ipairs(h.commands) do assert(command[1]~='keypress') end
end)
test('changing external subtitle removes prior external track from memory',function()
    local h=harness(); h:load(); local item=h:caption('Auto-generated'); h:activate(item)
    h.jobs[1].callback(true,{status=0})
    if h.observers and h.observers['sid'] then h.observers['sid']('sid', 3) end
    local item2=h:caption('Auto-translated'); h:activate(item2)
    h.jobs[2].callback(true,{status=0})
    if h.observers and h.observers['sid'] then h.observers['sid']('sid', 4) end
    local found_remove = false
    for _, c in ipairs(h.commands) do
        if c[1] == 'sub-remove' and c[2] == '3' then found_remove = true end
    end
    assert(found_remove)
end)
test('translated track without cookies uses fast-path translation pipeline',function()
    local h=harness(); h:load()
    local item=h:caption('Auto-translated'); h:activate(item)
    -- In standard mock harness without translator on disk, it tries curl
    eq(#h.jobs,1)
    assert(h.jobs[1].command.args[1]:find('curl'))
end)
print('Caption tests passed: '..count)
