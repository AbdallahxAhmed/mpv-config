-- Spec 005: playlist drag-to-reorder payload (tools/uosc_patches/playlist_reorder.lua).
-- The payload is loaded with dofile against stubs standing in for uosc (research R10).
local total = 0
local function eq(a, b, what) assert(a == b, (what or '') .. ': ' .. tostring(a) .. ' ~= ' .. tostring(b)) end
local function test(name, fn) fn(); total = total + 1; print('ok playlist_reorder: ' .. name) end

local here = debug.getinfo(1, 'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or '.') .. '/'
local PAYLOAD = here .. '../../tools/uosc_patches/playlist_reorder.lua'

-- ── uosc stand-ins ────────────────────────────────────────────────────
function clamp(min, value, max) return math.max(min, math.min(value, max)) end  -- lib/std.lua:6
function round(number) return math.floor(number + 0.5) end                      -- lib/std.lua:11
local renders = 0
function request_render() renders = renders + 1 end
state, display, fg, bg = {scale = 1}, {width = 1000, height = 800}, 'FFFFFF', '000000'

-- uosc's cursor bus (lib/cursor.lua:129-175): zone handler first, then every
-- global handler over the LIVE table, so a handler added inside the zone
-- handler runs in the same press; cursor:off removes from that same table.
cursor = {x = 50, y = 0, handlers = {primary_down = {}, primary_up = {}}, zones = {}}
function cursor:on(event, callback)
    local list = self.handlers[event]
    list[#list + 1] = callback
    return function()
        for i, f in ipairs(list) do if f == callback then table.remove(list, i) break end end
    end
end
function cursor:zone(event, rect, fn) self.zones[#self.zones + 1] = {event = event, rect = rect, fn = fn} end
function cursor:trigger(event, zone_fn)
    if zone_fn then zone_fn() end
    for _, callback in ipairs(self.handlers[event]) do callback() end
end
local function handler_count() return #cursor.handlers.primary_down + #cursor.handlers.primary_up end

-- mp: timers are recorded and run by the test; the playlist is the menu's emulated one
local timers, focused_value, observer = {}, true, nil
local current_playlist
local function flush()
    local due = timers
    timers = {}
    for _, fn in ipairs(due) do fn() end
end
_G.mp = nil  -- reassigned below, so the runner's wrapper adds mp.log (print goes through it)
mp = {
    log = function() end,
    get_time = function() return 0 end,
    get_property_native = function(name) if name == 'focused' then return focused_value end end,
    get_property = function(name)
        local i = tonumber(name:match('^playlist/(%d+)/filename$'))
        return i and current_playlist and current_playlist[i + 1] or nil
    end,
    get_property_number = function(name)
        if name == 'playlist-count' and current_playlist then return #current_playlist end
    end,
    observe_property = function(_, _, fn) observer = fn end,
    unobserve_property = function(fn) if fn == observer then observer = nil end end,
    add_timeout = function(_, fn) timers[#timers + 1] = fn; return {kill = function() end} end,
}

Menu = {}
dofile(PAYLOAD)

-- A playlist menu: 40 px rows from y = 100, items named f1..fn; move_selected_item_to
-- emulates upstream (Menu.lua:666-676) plus main.lua:895-898's playlist-move.
local function new_menu(n, overrides)
    local items, playlist = {}, {}
    for i = 1, n do items[i] = {title = 'f' .. i}; playlist[i] = 'f' .. i end
    local m = setmetatable({
        type = 'playlist', scroll_step = 40, item_height = 38, gap = 2, padding = 4, ax = 0,
        opacity = 1, proximity_raw = -10, mouse_nav = true, mouse_hovered_index = nil, moves = 0,
    }, {__index = Menu})
    m.current = {id = 'root', items = items, top = 100, height = 40 * n, scroll_y = 0, on_move = 'callback', width = 300}
    m.playlist = playlist
    current_playlist = playlist
    function m:create_action(fn) return fn end
    function m:set_scroll_by(delta) self.current.scroll_y = self.current.scroll_y + delta end
    function m:move_selected_item_to(to)
        local from = self.current.selected_index
        local index2 = to - (to > from and 0 or 1)       -- main.lua: playlist-move <from-1> <index2>
        local entry = table.remove(self.playlist, from)
        table.insert(self.playlist, (index2 > from - 1) and index2 or index2 + 1, entry)
        self.moves = self.moves + 1
    end
    for k, v in pairs(overrides or {}) do m[k] = v end
    return m
end

local function row_y(m, row) return m.current.top + 40 * (row - 1) + 20 end
local function press(m, row) cursor.y = row_y(m, row); cursor:trigger('primary_down', function() m:reorder_start(row) end) end
local function move(m, y, x) cursor.x = x or 50; cursor.y = y; m:reorder_move() end
local function release(m) cursor:trigger('primary_up'); flush() end
local function position_of(m, name) for i, v in ipairs(m.playlist) do if v == name then return i end end end
local function reset() timers, focused_value, observer, cursor.x = {}, true, nil, 50; cursor.handlers = {primary_down = {}, primary_up = {}} end

-- ── tests ─────────────────────────────────────────────────────────────

test('pointer → gap follows the data-model worked example', function()
    reset()
    local m = new_menu(5)
    for _, case in ipairs({{90, 0}, {115, 0}, {130, 1}, {175, 2}, {225, 3}, {290, 5}, {400, 5}}) do
        eq(case[2], m:reorder_gap(case[1]), 'y=' .. case[1])
    end
end)

test('a move under 4 px is a click: no drag, no move', function()
    reset()
    local m = new_menu(5)
    press(m, 1); move(m, row_y(m, 1) + 3); release(m)
    eq(0, m.moves); eq(nil, m.reorder); eq(0, handler_count())
end)

test('50 random drags land where the drop line showed, with one move at most', function()
    math.randomseed(5)
    for _ = 1, 50 do
        reset()
        local n = math.random(2, 30)
        local m = new_menu(n)
        local from = math.random(1, n)
        press(m, from); move(m, 100 + math.random(0, 40 * n - 1))
        local gap, name = m.reorder.gap, m.playlist[from]
        release(m)
        local to = gap < from and gap + 1 or gap
        eq(to, position_of(m, name), 'final position')
        assert(m.moves <= 1, 'more than one move')
        eq(to == from and 0 or 1, m.moves, 'moves')
        eq(nil, m.reorder); eq(nil, observer); eq(0, handler_count())
    end
end)

test('the commit waits one event-loop turn; Esc, close or a list update in it cancel', function()
    for _, how in ipairs({'esc', 'close', 'update'}) do
        reset()
        local m = new_menu(10)
        press(m, 1); move(m, row_y(m, 5))
        cursor:trigger('primary_up')                  -- the early up mpv sends before Esc
        eq(1, #timers, how .. ': one pending commit'); eq(0, m.moves, how .. ': no move yet')
        m:reorder_end()                                -- what the menu-key, close and update hooks call
        flush()
        eq(0, m.moves, how)
    end
end)

test('one timer per release; the gap and auto-scroll are frozen while pending', function()
    reset()
    local m = new_menu(10)
    press(m, 1); move(m, row_y(m, 5))
    local gap = m.reorder.gap
    cursor:trigger('primary_up'); cursor:trigger('primary_up')
    eq(1, #timers)
    move(m, row_y(m, 9)); cursor.y = 101; m:reorder_tick()
    eq(gap, m.reorder.gap); eq(0, m.current.scroll_y)
    flush(); eq(1, m.moves)
end)

test('outside is judged at the release, not at the commit', function()
    reset(); focused_value = nil
    local m = new_menu(10)
    press(m, 1); move(m, row_y(m, 5)); m.proximity_raw = 5
    cursor:trigger('primary_up'); m.proximity_raw = -10; flush()
    eq(0, m.moves)
end)

test('off-window on all four sides and math.huge: gap frozen, no scroll, no start', function()
    reset()
    local m = new_menu(10)
    press(m, 1); move(m, row_y(m, 4))
    local gap = m.reorder.gap
    for _, p in ipairs({{50, -30}, {50, 900}, {-5, 260}, {1200, 260}, {50, math.huge}}) do
        move(m, p[2], p[1])
        eq(gap, m.reorder.gap, 'gap at ' .. p[1] .. ',' .. p[2]); eq(0, m:reorder_depth())
    end
    m:reorder_end()
    reset()
    m = new_menu(10)
    press(m, 1); move(m, math.huge)
    eq(false, m.reorder.started); m:reorder_end()
end)

test('off-window release commits the frozen gap with focused, cancels without', function()
    reset()
    local m = new_menu(10)
    press(m, 1); move(m, row_y(m, 4)); local gap = m.reorder.gap
    move(m, -30); m.proximity_raw = 50; release(m)
    eq(gap, position_of(m, 'f1')); eq(1, m.moves)
    reset(); focused_value = nil
    m = new_menu(10)
    press(m, 1); move(m, row_y(m, 4)); move(m, -30); m.proximity_raw = 50; release(m)
    eq(0, m.moves)
end)

test('release outside the menu inside the window: commits with focused, cancels without', function()
    reset()
    local m = new_menu(10)
    press(m, 2); move(m, 80); m.proximity_raw = 5; release(m)
    eq(1, position_of(m, 'f2'))
    reset(); focused_value = nil
    m = new_menu(10)
    press(m, 2); move(m, 80); m.proximity_raw = 5; release(m)
    eq(0, m.moves)
end)

test('a press after the drag started cancels; its release moves nothing', function()
    reset()
    local m = new_menu(10)
    press(m, 1); move(m, row_y(m, 5))
    cursor:trigger('primary_down')
    eq(nil, m.reorder); eq(0, handler_count())
    release(m); eq(0, m.moves)
end)

test("the drag's own press does not trip the guard", function()
    reset()
    local m = new_menu(10)
    press(m, 3)                                       -- the guard runs in this same press
    assert(m.reorder, 'session survived its own press')
    m:reorder_end()
end)

test('a playlist change in the pending turn: no move', function()
    reset()
    local m = new_menu(10)
    press(m, 1); move(m, row_y(m, 5))
    cursor:trigger('primary_up')
    table.insert(m.playlist, 1, table.remove(m.playlist, 3))   -- another key moved an entry
    flush(); eq(0, m.moves)
    reset()
    m = new_menu(10)
    press(m, 1); move(m, row_y(m, 5))
    cursor:trigger('primary_up'); table.remove(m.playlist, 10); flush()
    eq(0, m.moves)
end)

test('focus: true → false cancels; unfocused at the press does not', function()
    reset()
    local m = new_menu(10)
    press(m, 1); move(m, row_y(m, 5))
    observer(nil, false)
    eq(nil, m.reorder); eq(nil, observer)
    reset(); focused_value = false
    m = new_menu(10)
    press(m, 1); observer(nil, false)
    assert(m.reorder, 'unfocused at the press must not cancel')
    observer(nil, true); observer(nil, false)
    eq(nil, m.reorder)
end)

test('search started during a drag: no outline, no auto-scroll, no move', function()
    reset()
    local m = new_menu(10)
    press(m, 1); move(m, row_y(m, 5)); m.current.search = {query = 'x'}
    local drawn = 0
    m:reorder_draw({rect = function() drawn = drawn + 1 end})
    cursor.y = 101; m:reorder_tick(); m:reorder_tick()
    release(m)
    eq(0, drawn); eq(0, m.current.scroll_y); eq(0, m.moves)
end)

test('start is refused: search, < 2 items, non-playlist, existing session', function()
    reset()
    local m = new_menu(5); m.current.search = {}; m:reorder_start(1); eq(nil, m.reorder)
    m = new_menu(1); m:reorder_start(1); eq(nil, m.reorder)
    m = new_menu(5, {type = 'subtitles'}); m:reorder_start(1); eq(nil, m.reorder)
    m = new_menu(5); m:reorder_start(1); local first = m.reorder
    m:reorder_start(2); eq(first, m.reorder); eq(2, handler_count())
    m:reorder_end(); eq(0, handler_count())
end)

test('start sets mouse_nav off and clears upstream scroll-drag and fling state', function()
    reset()
    local m = new_menu(10, {drag_last_y = 500, is_dragging = true})
    m.current.fling = {}
    m:reorder_start(1)
    eq(false, m.mouse_nav); eq(nil, m.drag_last_y); eq(false, m.is_dragging); eq(nil, m.current.fling)
    eq(1, m.current.selected_index)
    m:reorder_end()
end)

test('every exit restores hover state, so a still click never hits the held row', function()
    reset()
    local m = new_menu(10, {mouse_hovered_index = 3})
    press(m, 3); move(m, row_y(m, 6)); cursor:trigger('primary_down')
    eq(true, m.mouse_nav); eq(nil, m.mouse_hovered_index)
    reset()
    m = new_menu(10, {mouse_hovered_index = 2})
    press(m, 2); release(m)                            -- a still click on the handle
    eq(true, m.mouse_nav); eq(nil, m.mouse_hovered_index); eq(0, m.moves)
end)

test('auto-scroll: depth by zone, beyond the edge counts as full, dt capped at 0.1 s', function()
    reset()
    local m = new_menu(20, {})
    m.current.height = 400                              -- visible content: y 100..500
    cursor.y = 120; eq(-0.5, m:reorder_depth())
    cursor.y = 50; eq(-1, m:reorder_depth())
    cursor.y = 480; eq(0.5, m:reorder_depth())
    cursor.y = 700; eq(1, m:reorder_depth())
    cursor.y = 300; eq(0, m:reorder_depth())
    local now = 0
    mp.get_time = function() return now end
    press(m, 1); move(m, row_y(m, 2)); cursor.y = 700
    m:reorder_tick(); eq(0, m.current.scroll_y, 'first tick has dt 0')
    now = 5; m:reorder_tick()
    eq(1 * 12 * 40 * 0.1, m.current.scroll_y, 'dt capped at 0.1 s')
    mp.get_time = function() return 0 end
    m:reorder_end()
end)

test('handle: drawn left of the actions on the hovered row only, zone only without a session', function()
    reset()
    local m = new_menu(5, {mouse_hovered_index = 2})
    local icons = 0
    local ass = {icon = function() icons = icons + 1 end}
    local rect = {ax = 200, ay = 140, bx = 260, by = 178}
    cursor.zones = {}
    local ax = m:reorder_handle(ass, m.current, 2, rect, '')
    eq(1, icons); eq(200 - 4 - 38, ax); eq(1, #cursor.zones); eq('primary_down', cursor.zones[1].event)
    eq(200, m:reorder_handle(ass, m.current, 3, rect, ''), 'not the hovered row')
    m.proximity_raw = 5
    eq(200, m:reorder_handle(ass, m.current, 2, rect, ''), 'pointer outside the menu')
    m.proximity_raw = -10
    cursor.zones[1].fn()                                -- press on the handle zone
    cursor.zones = {}
    m:reorder_handle(ass, m.current, 2, rect, '')
    eq(0, #cursor.zones, 'no zone while a session exists')
    m:reorder_end()
end)

test('drawing: outline in bg on the playing row, never writes item.active', function()
    reset()
    local m = new_menu(5)
    m.current.items[1].active = true
    press(m, 1); move(m, row_y(m, 4))
    local colors = {}
    m:reorder_draw({rect = function(_, _, _, _, _, style) colors[#colors + 1] = style.color end})
    eq(5, #colors); eq(bg, colors[1]); eq(fg, colors[5])
    eq(true, m.current.items[1].active); eq(nil, m.current.items[2].active)
    m:reorder_end()
end)

test('a release in another (sub)menu moves nothing', function()
    reset()
    local m = new_menu(10)
    press(m, 1); move(m, row_y(m, 5)); m.current = {id = 'sub', items = m.current.items}
    release(m); eq(0, m.moves)
end)

print('Playlist reorder tests passed: ' .. total)
