-- help_overlay.lua - a one-key cheat sheet for this configuration.
--
-- mpv's own "?" prints the raw binding list, which mixes in every default
-- and says nothing about the mouse-first parts of this configuration. This
-- shows the curated list instead, grouped by what you actually do.
--
-- The list also spells out the Arabic layout story: mpv sees the character
-- a key produces, so the deployer-generated same-key twins (c a n ? ...) and
-- the layout-independent Ctrl+Shift+ backups (h g b G B actions) are the
-- keys that work in both layouts.

local msg = require 'mp.msg'

local SECTIONS = {
    {
        title = "PLAYBACK",
        rows = {
            { "space / k", "pause and resume" },
            { "arrows", "seek (up/down = 1 minute)" },
            { "m", "mute" },
            { "f", "fullscreen" },
            { "F3 / F4", "toggle deband / interpolation" },
            { "Alt+t", "motion scaler: oversample <-> linear" },
            { "Ctrl+Alt+m", "Smart Motion on/off" },
        },
    },
    {
        title = "VIDEO",
        rows = {
            { "Ctrl+1..Ctrl+6", "Anime4K mode A / B / C / A+A / B+B / C+A" },
            { "Ctrl+0", "shaders off" },
            { "Ctrl+g", "cycle the Anime4K mode" },
            { "F5 / F6 / F7", "cycle audio / subtitle / subtitle visibility" },
            { "F8", "stable volume filter" },
            { "F1 / F2", "screenshot without / with subtitles" },
        },
    },
    {
        title = "SUBTITLES & MENUS",
        rows = {
            { "c / Ctrl+c", "caption menu / YouTube subtitle menu" },
            { "a", "audio & dubs menu" },
            { "n", "subtitle sync menu" },
            { "h", "playback history" },
            { "b", "subtitle background box" },
            { "g / G", "SponsorBlock: mark segment / submit" },
            { "Ctrl+v", "paste the clipboard link and play it" },
            { "?", "this cheat sheet" },
        },
    },
    {
        title = "MOUSE",
        rows = {
            { "menu button", "quality, audio, captions, download, help" },
            { "right click", "context menu" },
            { "double click", "fullscreen" },
            { "scroll", "seek / volume" },
        },
    },
    {
        title = "KEYBOARD LAYOUT",
        rows = {
            { "c a n ?", "same physical key in Arabic (generated twins)" },
            { "Shift+h m s b u", "history mark submit backdrop upvote (Arabic, no Ctrl)" },
            { "h g b G B", "bare keys alias under Arabic - Shift or Ctrl+Shift routes" },
            { "Ctrl+Shift+t", "manual anime-detection override (was Ctrl+Shift+g)" },
            { "Ctrl+<letter>", "always the Latin key (Windows control codes)" },
            { "F-keys, space", "layout independent" },
            { "Alt+<letter>", "layout dependent - use the mouse menu" },
        },
    },
}

local function build()
    local lines = {}
    for _, section in ipairs(SECTIONS) do
        lines[#lines + 1] = "{\\b1}" .. section.title .. "{\\b0}"
        for _, row in ipairs(section.rows) do
            lines[#lines + 1] = string.format("  {\\b0}%s{\\b0}   %s", row[1], row[2])
        end
    end
    return table.concat(lines, "\\N")
end

local function show()
    mp.osd_message(build(), 12)
end

mp.register_script_message("help", show)
mp.register_script_message("toggle-help", show)

-- This "?" binding covers Latin layouts; under Arabic the key produces
-- "؟" and the generated input.conf twin carries the same action (F9 is
-- the layout-independent fallback, bound in input.conf).
mp.add_key_binding("?", function() show() end)
mp.add_key_binding("F9", function() show() end)

_G.help_overlay = { SECTIONS = SECTIONS, build = build }
