-- sub_backdrop.lua - b toggles a translucent box behind plain-text subtitles.
--
-- Off (the default): sub-border-style=outline-and-shadow, mpv's own default,
-- where sub-back-color only colours the text shadow - exactly the deployed
-- look. On: sub-border-style=background-box, where the same sub-back-color
-- (the Netflix-style ~70%-alpha near-black "#B3080808") fills a box behind
-- the text. Only the border style is toggled, so switching off returns the
-- original rendering pixel for pixel. A fully transparent sub-back-color
-- would draw an invisible box, so "on" uses ON_FALLBACK then and "off" puts
-- the transparent colour back.
-- Keys live in input.conf: b and the Arabic twin -> script-binding sub_backdrop/toggle

local BOX = "background-box"
local PLAIN = "outline-and-shadow"
-- Must match the sub-back-color styling default in config/mpv.conf.template.
-- tests/test_sub_backdrop_toggle.py keeps the two constants in sync.
local ON_FALLBACK = "#B3080808"

local replaced_color = nil  -- a transparent colour swapped out while "on"

local function is_transparent(color)
    -- mpv renders colors back as #AARRGGBB (m_option.c print_color)
    return type(color) == "string" and color:upper():sub(1, 3) == "#00"
end

local function toggle()
    if mp.get_property("sub-border-style") == BOX then
        mp.set_property("sub-border-style", PLAIN)
        if replaced_color then
            mp.set_property("sub-back-color", replaced_color)
            replaced_color = nil
        end
        mp.osd_message("Subtitle backdrop: off", 1.6)
    else
        local color = mp.get_property("sub-back-color")
        if is_transparent(color) then
            replaced_color = color
            mp.set_property("sub-back-color", ON_FALLBACK)
        end
        mp.set_property("sub-border-style", BOX)
        mp.osd_message("Subtitle backdrop: on", 1.6)
    end
end

-- Keyless registration: input.conf owns the key (b and its Arabic twin share this binding).
mp.add_key_binding(nil, "toggle", toggle)
