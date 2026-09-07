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
    local h={filters=filters or {},messages={},writes=0,sends=0,ui_ready=not no_ui}
    mp={get_script_name=function() return 'player_toolbar' end,
        get_property_native=function(k,d) eq(k,'af'); return h.filters end,
        set_property_native=function(k,value)
            eq(k,'af'); h.writes=h.writes+1
            if h.fail then return false,'test failure' end
            h.filters=value; h.observer('af',value); return true
        end,
        observe_property=function(k,t,fn) eq(k,'af');eq(t,'native');h.observer=fn end,
        register_script_message=function(name,fn) h.messages[name]=fn end,
        add_key_binding=function() error('Mouse controls must not require a keyboard binding') end,
        add_periodic_timer=function() error('Toolbar must not poll') end,
        add_timeout=function() error('Toolbar must not start a timer') end,
        commandv=function(...)
            h.arg_count=select('#',...);eq(h.arg_count,5)
            if not h.ui_ready then error('uosc has not started yet') end
            local c={...};eq(c[1],'script-message-to');eq(c[2],'uosc');eq(c[3],'set-button');eq(c[4],'stable-volume')
            h.button=c[5];h.sends=h.sends+1
        end,
        osd_message=function(text) h.osd=text end}
    package.loaded['mp.utils']=nil;package.loaded['mp.msg']=nil
    package.preload['mp.utils']=function() return {format_json=function(value) return value,nil end} end
    package.preload['mp.msg']=function() return {warn=function() end} end
    dofile('scripts/player-toolbar.lua')
    function h:click()
        local c=self.button.command;eq(c[1],'script-message-to');eq(c[2],'player_toolbar')
        self.messages[c[3]]()
    end
    return h
end
test('startup publishes a distinct inactive icon without changing audio',function()
    local h=harness();eq(h.writes,0);eq(h.button.icon,'compress');eq(h.button.active,false)
    eq(h.button.badge,nil);eq(h.button.tooltip,'Stable volume: Off')
end)
test('the icon command toggles audio without any physical key binding',function()
    local h=harness();h:click();eq(h.writes,1);eq(#h.filters,1);eq(h.filters[1].label,label)
    eq(h.filters[1].params.graph,graph);eq(h.button.active,true);eq(h.button.badge,'ON')
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
    eq(h.sends,before+1);h:click();h.messages['uosc-version']('5.13.0');eq(h.button.active,true)
end)
test('partially disabled legacy preset is replaced without duplicate filters',function()
    local old={filter(normalizer,nil,false),filter(limiter)};local h=harness(old)
    eq(h.button.active,false);h:click();eq(#h.filters,1);eq(h.filters[1].params.graph,graph)
    eq(#old,2);eq(old[1].enabled,false)
end)
test('uosc can start later without aborting the toolbar script',function()
    local h=harness({},true);eq(h.writes,0);eq(h.button,nil)
    eq(type(h.messages['toggle-stable-volume']),'function')
    h.ui_ready=true;h.messages['uosc-version']('5.13.0');eq(h.button.icon,'compress')
    h:click();eq(h.button.active,true)
end)
test('JSON secondary returns never become extra command arguments',function()
    local h=harness();eq(h.arg_count,5);h:click();eq(h.arg_count,5)
    h:click();eq(h.arg_count,5);eq(h.button.badge,nil)
end)
print('Toolbar tests passed: '..total)
