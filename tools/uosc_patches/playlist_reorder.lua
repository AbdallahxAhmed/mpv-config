-- Playlist drag-to-reorder (mpv-config spec 005). Session: self.reorder, nil when idle.
local REORDER_THRESHOLD, REORDER_ROWS_PER_S = 4, 12

-- Pointer left the window: hover lost (math.huge), or held-button coordinates outside it.
local function reorder_off_window()
	return cursor.y == math.huge or cursor.x < 0 or cursor.y < 0 or cursor.x >= display.width or cursor.y >= display.height
end

---@param menu? MenuStack
function Menu:reorder_enabled(menu)
	menu = menu or self.current
	return self.type == 'playlist' and menu == self.current and menu.on_move ~= nil
		and not menu.search and #menu.items >= 2
end

---@param y number
function Menu:reorder_gap(y)
	local menu = self.current
	local gap = math.floor((y - menu.top + menu.scroll_y) / self.scroll_step + 0.5)
	return clamp(0, gap, #menu.items)
end

---@param index integer
function Menu:reorder_start(index)
	if self.reorder or not self:reorder_enabled() then return end
	local session = {menu_id = self.current.id, from = index, gap = index, press_y = cursor.y, started = false,
		file = mp.get_property('playlist/' .. (index - 1) .. '/filename')}
	session.focused = mp.get_property_native('focused')
	if session.focused ~= nil then
		session.on_focus = function(_, focused)
			if focused == false and session.focused then self:reorder_end() else session.focused = focused end
		end
		mp.observe_property('focused', 'bool', session.on_focus)
	end
	-- the drag's own release reaches uosc wherever it happens; a press after it started means uosc dropped it
	session.off_up = cursor:on('primary_up', function() self:reorder_release() end)
	session.off_down = cursor:on('primary_down', function() if session.started then self:reorder_end() end end)
	self.reorder = session
	self.current.selected_index = index
	self.mouse_nav, self.drag_last_y, self.is_dragging, self.current.fling = false, nil, false, nil -- no upstream scroll state survives
	request_render()
end

function Menu:reorder_end()
	local session = self.reorder
	if not session then return end
	self.reorder = nil
	if session.on_focus then mp.unobserve_property(session.on_focus) end
	session.off_up()
	session.off_down()
	self.mouse_nav, self.mouse_hovered_index = true, nil -- hover-select resumes; a still click acts on the row under it
	request_render()
	return session
end

function Menu:reorder_move()
	local session = self.reorder
	if reorder_off_window() or session.outside ~= nil then return request_render() end
	if not session.started and math.abs(cursor.y - session.press_y) >= REORDER_THRESHOLD * state.scale then
		session.started = true
	end
	if session.started then session.gap = self:reorder_gap(cursor.y) end
	request_render()
end

-- mpv sends the button-up early when Esc is pressed while it is held (and on focus-out), so the
-- commit waits one event-loop turn: Esc, close or a list update queued behind it cancel the session.
function Menu:reorder_release()
	local session = self.reorder
	if not session or session.outside ~= nil then return end
	session.outside = reorder_off_window() or self.proximity_raw > 0
	mp.add_timeout(0, function() if self.reorder == session then self:reorder_commit() end end)
end

function Menu:reorder_commit()
	local session = self:reorder_end()
	if not session.started or self.current.id ~= session.menu_id or self.current.search then return end
	if session.outside and not session.on_focus then return end
	-- a key handled in the pending turn may have changed the playlist before Menu:update arrives
	if mp.get_property_number('playlist-count') ~= #self.current.items
		or mp.get_property('playlist/' .. (session.from - 1) .. '/filename') ~= session.file then return end
	local to = session.gap < session.from and session.gap + 1 or session.gap
	if to ~= session.from then
		self.current.selected_index = session.from
		self:move_selected_item_to(to)
	end
end

---@return number -1..1, negative in the top zone, positive in the bottom zone
function Menu:reorder_depth()
	local menu, y, zone = self.current, cursor.y, self.scroll_step
	if reorder_off_window() then return 0 end
	if y < menu.top + zone then return -clamp(0, (menu.top + zone - y) / zone, 1) end
	local bottom = menu.top + menu.height
	if y > bottom - zone then return clamp(0, (y - bottom + zone) / zone, 1) end
	return 0
end

function Menu:reorder_tick()
	local session = self.reorder
	if not session.started or self.current.search or session.outside ~= nil then return end
	local depth, now = self:reorder_depth(), mp.get_time()
	if depth == 0 then
		session.last_tick = nil
		return
	end
	local dt = session.last_tick and math.min(now - session.last_tick, 0.1) or 0
	session.last_tick = now
	self:set_scroll_by(depth * REORDER_ROWS_PER_S * self.scroll_step * dt)
	session.gap = self:reorder_gap(cursor.y)
	request_render()
end

---@return number new left edge of the actions rectangle
function Menu:reorder_handle(ass, menu, index, actions_rect, clip)
	local session = self.reorder
	local shown = session and session.from == index
		or (not session and self.mouse_nav and self.mouse_hovered_index == index and self.proximity_raw <= 0)
	if not shown or not self:reorder_enabled(menu) then return actions_rect.ax end
	local margin, size = self.gap * 2, actions_rect.by - actions_rect.ay
	local rect = {ax = actions_rect.ax - margin - size, ay = actions_rect.ay, bx = actions_rect.ax - margin, by = actions_rect.by}
	ass:icon(rect.ax + size / 2, rect.ay + size / 2, size * 0.66, 'drag_handle', {
		color = fg, opacity = self.opacity, clip = clip,
	})
	if not session then
		cursor:zone('primary_down', rect, self:create_action(function() self:reorder_start(index) end))
	end
	return rect.ax
end

function Menu:reorder_draw(ass)
	local session, menu = self.reorder, self.current
	if not session.started or menu.id ~= session.menu_id or menu.search then return end
	local ax, bx = self.ax + self.padding, self.ax + self.padding + menu.width
	local top, bottom = menu.top, menu.top + menu.height
	local t = round(2 * state.scale)
	local clip = '\\clip(0,' .. top .. ',' .. display.width .. ',' .. bottom .. ')'
	local held = menu.items[session.from]
	local outline = {color = held and held.active and bg or fg, opacity = self.opacity, clip = clip}
	local ay = top - menu.scroll_y + self.scroll_step * (session.from - 1)
	local by = ay + self.item_height
	ass:rect(ax, ay, bx, ay + t, outline)
	ass:rect(ax, by - t, bx, by, outline)
	ass:rect(ax, ay, ax + t, by, outline)
	ass:rect(bx - t, ay, bx, by, outline)
	local y = top - menu.scroll_y + self.scroll_step * session.gap - (self.scroll_step - self.item_height) / 2
	y = clamp(top + t / 2, y, bottom - t / 2)
	ass:rect(ax, y - t / 2, bx, y + t / 2, {color = fg, opacity = self.opacity, clip = clip})
end
