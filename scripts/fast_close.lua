-- scripts/fast_close.lua
-- Instant window close on Linux / Wayland: minimize the window surface
-- immediately upon shutdown or quit to eliminate visible freezes while
-- Vulkan / libplacebo / Wayland teardown completes.

local is_linux = (package.config:sub(1, 1) == "/")

local function fast_quit(watch_later)
    if is_linux then
        pcall(mp.set_property, "window-minimized", "yes")
    end
    if watch_later then
        mp.command("quit-watch-later")
    else
        mp.command("quit")
    end
end

if is_linux then
    mp.register_event("shutdown", function()
        pcall(mp.set_property, "window-minimized", "yes")
    end)
end

mp.add_key_binding(nil, "quit", function() fast_quit(false) end)
mp.add_key_binding(nil, "quit-watch-later", function() fast_quit(true) end)
