-- sub_backdrop.lua - Subtitle background-box toggle with a readable OSD
-- The backdrop is the translucent rectangle mpv draws behind subtitle text
-- (sub-back-color). The deployed styling in mpv.conf is the Netflix-style
-- ~70%-alpha near-black box "#B3080808"; "#00000000" is the transparent
-- "cinema" look. mpv's built-in cycle-values feedback shows the raw property
-- name and hex; this toggle shows "Subtitle backdrop: on/off" instead.
-- Keys live in input.conf: b and the Arabic twin ب -> script-binding sub_backdrop/toggle
-- mpv renders colors back as #AARRGGBB (m_option.c print_color), so the
-- exact-string comparisons below round-trip bit-identically on every OS.

local OFF = "#00000000" -- fully transparent = backdrop off
-- Must match the sub-back-color styling default in config/mpv.conf.template.
-- tests/test_sub_backdrop_toggle.py keeps the two constants in sync.
local ON_FALLBACK = "#B3080808"

local last_on = nil

local function toggle()
    local value = mp.get_property("sub-back-color", OFF)
    if value == OFF then
        mp.set_property("sub-back-color", last_on or ON_FALLBACK)
        mp.osd_message("Subtitle backdrop: on", 1.6)
    else
        last_on = value
        mp.set_property("sub-back-color", OFF)
        mp.osd_message("Subtitle backdrop: off", 1.6)
    end
end

-- Keyless registration: input.conf owns the key (b and ب share this binding).
mp.add_key_binding(nil, "toggle", toggle)
