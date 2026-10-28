-- profile_picker: the anime detector and the Anime4K mode handling.
local total = 0
local function eq(a, b) assert(a == b, tostring(a) .. ' ~= ' .. tostring(b)) end
local function test(name, fn) fn(); total = total + 1; print('ok profile_picker: ' .. name) end

local here = debug.getinfo(1, 'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or './') .. '/'
if not here:match('[/\\]$') and here ~= './' then here = here .. '/' end

local SCRIPT = here .. '../../scripts/profile_picker.lua'

local function create_harness()
    _G.mp = nil
    local h = {props = {}, osds = {}, events = {}, observers = {}, commands = {}, files = {}, messages = {}, expanded_paths = {}}
    _G.mp = {
        log = function() end,
        msg = {info = function() end, warn = function() end, debug = function() end},
        get_property = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        get_property_native = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        get_property_bool = function(k, d) local v = h.props[k]; if v == nil then return d end; return v end,
        set_property = function(k, v) h.props[k] = v end,
        set_property_native = function(k, v) h.props[k] = v end,
        set_property_bool = function(k, v) h.props[k] = v end,
        osd_message = function(text, duration) h.osds[#h.osds + 1] = {text = text, duration = duration} end,
        commandv = function(...) h.commands[#h.commands + 1] = { ... } end,
        command_native = function(args)
            if type(args) == "table" and args[1] == "expand-path" and h.expanded_paths then
                return h.expanded_paths[args[2]]
            end
            return nil
        end,
        register_event = function(name, fn) h.events[name] = fn end,
        observe_property = function(name, typ, fn) h.observers[name] = fn end,
        register_script_message = function(name, fn) h.messages[name] = fn end,
        find_config_file = function() return nil end,
        get_config_dir = function() return nil end,
        get_opt = function() return nil end,
    }
    package.loaded['mp.options'] = nil
    package.preload['mp.options'] = function() return {
        read_options = function(o) end,
    } end
    return h
end

local function load_script()
    local h = create_harness()
    dofile(SCRIPT)
    return h, _G.profile_picker
end

local JPN = { { type = 'audio', lang = 'jpn', title = 'Japanese' } }
local ENG = { { type = 'audio', lang = 'eng', title = 'English' } }
local JPN_AND_ENG = {
    { type = 'audio', lang = 'jpn', title = 'Japanese' },
    { type = 'audio', lang = 'eng', title = 'English' },
}

-- ── detection ─────────────────────────────────────────────────────────

test('a known anime release group decides on its own', function()
    local _, pp = load_script()
    local v = pp.classify(
        'D:\\Anime\\[Erai-raws] JoJo no Kimyou na Bouken - Steel Ball Run - 05 [1080p NF WEBRip HEVC AAC][MultiSub][68E0C6CB].mkv',
        ENG)
    eq(true, v.anime)
    assert(v.score >= 4)
end)

test('a SubsPlease release is detected without a group tag', function()
    local _, pp = load_script()
    local v = pp.classify(
        'D:\\Video\\Frieren - 01 [1080p].mkv', JPN_AND_ENG)
    eq(true, v.anime)
end)

test('an Anime Time release is detected', function()
    local _, pp = load_script()
    local v = pp.classify('D:\\Video\\Some Show - 12 [720p].mkv', JPN)
    eq(true, v.anime)
end)

test('a Japanese live-action film is not anime', function()
    local _, pp = load_script()
    local v = pp.classify('D:\\Films\\Perfect Blue 1997 [1080p].mkv', JPN_AND_ENG)
    eq(false, v.anime)
end)

-- 2026-10-28 CachyOS report: files under /mnt/Data/Entertainment/Anime/
-- scored only +1 for the folder (threshold 3) and fell through to
-- live-action, overriding mpv's own [protocol.file] anime profile. The
-- directory names the medium, so the folder signal now decides on its own.
test('a film in a folder named Anime is anime (folder decides)', function()
    local _, pp = load_script()
    local v = pp.classify('D:\\Anime\\Some Hollywood Movie 2019 [1080p].mkv', ENG)
    eq(true, v.anime)
end)

test('a donghua episode is detected by its folder alone', function()
    local _, pp = load_script()
    local v = pp.classify(
        '/mnt/Data/Entertainment/Donghua/Thousand Autumns - 05 [1080p].mkv', ENG)
    eq(true, v.anime)
end)

test('the folder signal survives a strict threshold', function()
    local _, pp = load_script()
    local v = pp.classify('/mnt/Data/Entertainment/Anime Series/Show - 01.mkv',
        ENG, { groups = {}, series = {}, threshold = 5 })
    eq(true, v.anime)
end)

test('a Hollywood movie with a MultiSub tag is not anime', function()
    local _, pp = load_script()
    local v = pp.classify('D:\\Films\\Movie [1080p][MultiSub].mkv', ENG)
    eq(false, v.anime)
end)

test('the series list is a hint, not a verdict', function()
    local _, pp = load_script()
    -- on its own it does not decide: the list changes with every season,
    -- so it must never outvote the signals that keep working
    local alone = pp.classify('D:\\Video\\My Show 07 [1080p].mkv', ENG,
        { groups = {}, series = { 'my show' }, threshold = 3 })
    eq(false, alone.anime)
    -- but it pushes a borderline file over the line
    local hint = pp.classify('D:\\Video\\My Show 07 [1080p].mkv', JPN,
        { groups = {}, series = { 'my show' }, threshold = 3 })
    eq(true, hint.anime)
end)

test('the threshold is honoured', function()
    local _, pp = load_script()
    local v = pp.classify('D:\\Video\\Show - 05 [1080p].mkv', JPN,
        { groups = {}, series = {}, threshold = 3 })
    eq(true, v.anime)
    local strict = pp.classify('D:\\Video\\Show - 05 [1080p].mkv', JPN,
        { groups = {}, series = {}, threshold = 4 })
    eq(false, strict.anime)
end)

test('the path is not the only signal: a clean name still works', function()
    local _, pp = load_script()
    local v = pp.classify('/home/user/Videos/Steins Gate - 01.mkv', JPN)
    eq(true, v.anime)
end)

test('the episode marker recognizes every common form', function()
    local _, pp = load_script()
    eq(true, pp.has_episode_marker('Show - 05 [1080p].mkv'))
    eq(true, pp.has_episode_marker('Show E05.mkv'))
    eq(true, pp.has_episode_marker('Show EP05.mkv'))
    eq(true, pp.has_episode_marker('Show Episode 05.mkv'))
    eq(true, pp.has_episode_marker('Show S01E05.mkv'))
    eq(false, pp.has_episode_marker('Show 2019 [1080p].mkv'))
end)

test('the Japanese audio track is found in any of its forms', function()
    local _, pp = load_script()
    eq(true, pp.has_jpn_audio({ { type = 'audio', lang = 'jpn' } }))
    eq(true, pp.has_jpn_audio({ { type = 'audio', lang = 'ja' } }))
    eq(true, pp.has_jpn_audio({ { type = 'audio', title = 'Japanese' } }))
    eq(true, pp.has_jpn_audio({ { type = 'audio', title = 'JPN' } }))
    eq(false, pp.has_jpn_audio({ { type = 'audio', lang = 'eng' } }))
    eq(false, pp.has_jpn_audio({ { type = 'sub', lang = 'jpn' } }))
    eq(false, pp.has_jpn_audio({}))
    eq(false, pp.has_jpn_audio(nil))
end)

test('the title cleaner drops the release noise but keeps the title', function()
    local _, pp = load_script()
    local cleaned = pp.clean_title(
        '[Erai-raws] JoJo no Kimyou na Bouken - Steel Ball Run - 05 [1080p NF WEBRip HEVC AAC][MultiSub][68E0C6CB].mkv')
    assert(cleaned:find('jojo no kimyou na bouken', 1, true), cleaned)
    assert(not cleaned:find('webrip', 1, true), cleaned)
    assert(not cleaned:find('multisub', 1, true), cleaned)
    assert(not cleaned:find('erai', 1, true), cleaned)
end)

-- ── behaviour ─────────────────────────────────────────────────────────

test('the anime profile is applied when the file is anime', function()
    local h, pp = load_script()
    h.props['path'] = 'D:\\Video\\[Erai-raws] Show - 05 [1080p].mkv'
    h.props['track-list'] = JPN
    h.events['file-loaded']()
    eq('apply-profile', h.commands[1][1])
    eq('anime', h.commands[1][2])
end)

test('the live-action profile is applied for everything else', function()
    local h, pp = load_script()
    h.props['path'] = 'D:\\Films\\Movie [1080p].mkv'
    h.props['track-list'] = ENG
    h.events['file-loaded']()
    eq('apply-profile', h.commands[1][1])
    eq('live-action', h.commands[1][2])
end)

test('the profile is not re-applied for every file of the same kind', function()
    local h, pp = load_script()
    h.props['track-list'] = JPN
    h.props['path'] = 'D:\\Video\\[Erai-raws] A - 01 [1080p].mkv'
    h.events['file-loaded']()
    local after_first = #h.commands
    h.props['path'] = 'D:\\Video\\[Erai-raws] A - 02 [1080p].mkv'
    h.events['file-loaded']()
    eq(after_first, #h.commands)
end)

test('the Anime4K mode is applied with the anime profile', function()
    local h, pp = load_script()
    h.props['path'] = 'D:\\Video\\[Erai-raws] Show - 05 [1080p].mkv'
    h.props['track-list'] = JPN
    h.events['file-loaded']()
    local chain = h.props['glsl-shaders']
    eq('table', type(chain))
    local joined = table.concat(chain, '\1')
    assert(joined:find('Anime4K_Restore_CNN_VL', 1, true), joined)
    assert(joined:find('Anime4K_Restore_CNN_M', 1, true), joined)
    assert(joined:find('~~/shaders/', 1, true), joined)
end)

test('a manual chain change is recognised and persisted', function()
    local h, pp = load_script()
    h.props['path'] = 'D:\\Video\\[Erai-raws] Show - 05 [1080p].mkv'
    h.props['track-list'] = JPN
    h.events['file-loaded']()
    eq('A+A', pp.state.mode)
    -- the user pressed Ctrl+2: the chain changes under our feet. This is
    -- exactly the chain the shipped Ctrl+2 binding writes.
    h.observers['glsl-shaders']('glsl-shaders',
        '~~/shaders/Anime4K_Clamp_Highlights.glsl;'
        .. '~~/shaders/Anime4K_Restore_CNN_Soft_VL.glsl;'
        .. '~~/shaders/Anime4K_Upscale_CNN_x2_VL.glsl;'
        .. '~~/shaders/Anime4K_AutoDownscalePre_x2.glsl;'
        .. '~~/shaders/Anime4K_AutoDownscalePre_x4.glsl;'
        .. '~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl')
    eq('B', pp.state.mode)
end)

test('the mode cycle walks the list and reports through the OSD', function()
    local h, pp = load_script()
    eq(true, pp.set_mode('B'))
    eq('B', pp.state.mode)
    assert(#h.osds >= 1)
    assert(h.osds[#h.osds].text:find('B', 1, true))
    eq(false, pp.set_mode('nonsense'))
end)

test('an empty chain is not a mode change', function()
    local h, pp = load_script()
    h.props['path'] = 'D:\\Video\\Show - 05 [1080p].mkv'
    h.props['track-list'] = JPN
    h.events['file-loaded']()
    -- the base configuration has no shaders: that is not the user asking
    -- for "off"
    h.observers['glsl-shaders']('glsl-shaders', '')
    eq('A+A', pp.state.mode)
end)

test('the profile own chain is not mistaken for a user choice', function()
    local h, pp = load_script()
    h.props['path'] = 'D:\\Video\\[Erai-raws] Show - 05 [1080p].mkv'
    h.props['track-list'] = JPN
    h.events['file-loaded']()
    eq('A+A', pp.state.mode)
    -- mpv applies the profile's chain right after the profile is applied;
    -- the observer must ignore it
    h.observers['glsl-shaders']('glsl-shaders',
        '~~/shaders/Anime4K_Clamp_Highlights.glsl;'
        .. '~~/shaders/Anime4K_Restore_CNN_VL.glsl;'
        .. '~~/shaders/Anime4K_Upscale_CNN_x2_VL.glsl;'
        .. '~~/shaders/Anime4K_Restore_CNN_M.glsl;'
        .. '~~/shaders/Anime4K_AutoDownscalePre_x2.glsl;'
        .. '~~/shaders/Anime4K_AutoDownscalePre_x4.glsl;'
        .. '~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl')
    eq('A+A', pp.state.mode)
end)

test('a stream is classified but keeps the light profile', function()
    local h, pp = load_script()
    h.props['path'] = 'https://www.youtube.com/watch?v=abc'
    h.props['track-list'] = JPN
    h.events['file-loaded']()
    -- the anime profile would bring Anime4K, which measurably disturbs the
    -- 144Hz cadence on a stream: it is opt-in there (Ctrl+1..6)
    eq(1, #h.commands)
    eq('apply-profile', h.commands[1][1])
    eq('live-action', h.commands[1][2])
end)

test('a local anime file gets the anime profile and active verification OSD', function()
    local h, pp = load_script()
    h.props['path'] = 'D:\\Video\\[Erai-raws] Show - 05 [1080p].mkv'
    h.props['track-list'] = JPN
    h.events['file-loaded']()
    eq(1, #h.commands)
    eq('apply-profile', h.commands[1][1])
    eq('anime', h.commands[1][2])
    local found_osd = false
    for _, osd in ipairs(h.osds) do
        if osd.text:find('Anime Detected: Anime4K %[A%+A%] Active') then
            found_osd = true
        end
    end
    assert(found_osd, "Anime detection OSD notification was not shown")
end)

test('mode_file_path resolves correctly on Linux via expand-path', function()
    local h, pp = load_script()
    h.expanded_paths['~~/script-opts/anime4k.conf'] = '/home/user/.config/mpv/script-opts/anime4k.conf'
    eq('/home/user/.config/mpv/script-opts/anime4k.conf', pp.mode_file_path())
end)

test('mode_file_path resolves correctly on Windows via expand-path', function()
    local h, pp = load_script()
    h.expanded_paths['~~/script-opts/anime4k.conf'] = 'C:/Users/User/AppData/Roaming/mpv/script-opts/anime4k.conf'
    eq('C:/Users/User/AppData/Roaming/mpv/script-opts/anime4k.conf', pp.mode_file_path())
end)

test('chain_for returns the shader list as a table', function()
    local _, pp = load_script()
    local chain = pp.chain_for('A')
    eq('table', type(chain))
    eq(6, #chain)
    eq('~~/shaders/Anime4K_Clamp_Highlights.glsl', chain[1])
    eq('table', type(pp.chain_for('off')))
    eq(0, #pp.chain_for('off'))
    eq(nil, pp.chain_for('nonsense'))
end)

test('a manual colon-joined chain change is recognised (POSIX serialization)', function()
    local h, pp = load_script()
    h.props['path'] = 'D:\\Video\\[Erai-raws] Show - 05 [1080p].mkv'
    h.props['track-list'] = JPN
    h.events['file-loaded']()
    eq('A+A', pp.state.mode)
    -- the same Ctrl+2 chain, serialized the way mpv lists render on Linux
    h.observers['glsl-shaders']('glsl-shaders',
        '~~/shaders/Anime4K_Clamp_Highlights.glsl:'
        .. '~~/shaders/Anime4K_Restore_CNN_Soft_VL.glsl:'
        .. '~~/shaders/Anime4K_Upscale_CNN_x2_VL.glsl:'
        .. '~~/shaders/Anime4K_AutoDownscalePre_x2.glsl:'
        .. '~~/shaders/Anime4K_AutoDownscalePre_x4.glsl:'
        .. '~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl')
    eq('B', pp.state.mode)
end)

test('the profile own colon-joined chain is not mistaken for a user choice', function()
    local h, pp = load_script()
    h.props['path'] = 'D:\\Video\\[Erai-raws] Show - 05 [1080p].mkv'
    h.props['track-list'] = JPN
    h.events['file-loaded']()
    eq('A+A', pp.state.mode)
    -- POSIX serialization of the [anime] profile's list, observed right
    -- after apply-profile: the expect guard must absorb it too
    h.observers['glsl-shaders']('glsl-shaders',
        '~~/shaders/Anime4K_Clamp_Highlights.glsl:'
        .. '~~/shaders/Anime4K_Restore_CNN_VL.glsl:'
        .. '~~/shaders/Anime4K_Upscale_CNN_x2_VL.glsl:'
        .. '~~/shaders/Anime4K_Restore_CNN_M.glsl:'
        .. '~~/shaders/Anime4K_AutoDownscalePre_x2.glsl:'
        .. '~~/shaders/Anime4K_AutoDownscalePre_x4.glsl:'
        .. '~~/shaders/Anime4K_Upscale_CNN_x2_M.glsl')
    eq('A+A', pp.state.mode)
end)

test('set_mode on a live-action file flips the profile and applies natively', function()
    local h, pp = load_script()
    h.props['path'] = 'D:\\Films\\Movie 2019 [1080p].mkv'
    h.props['track-list'] = ENG
    h.events['file-loaded']()
    eq('live-action', pp.state.applied)
    eq(true, pp.set_mode('A'))
    -- the profile flips so the live-action scaler never stacks on Anime4K
    local flipped = false
    for _, cmd in ipairs(h.commands) do
        if cmd[1] == 'apply-profile' and cmd[2] == 'anime' then flipped = true end
    end
    assert(flipped, 'live-action profile was not flipped to anime')
    local chain = h.props['glsl-shaders']
    eq('table', type(chain))
    eq('~~/shaders/Anime4K_Clamp_Highlights.glsl', chain[1])
    eq('A', pp.state.mode)
end)

test('set_mode off clears the shader list', function()
    local h, pp = load_script()
    eq(true, pp.set_mode('off'))
    local chain = h.props['glsl-shaders']
    eq('table', type(chain))
    eq(0, #chain)
end)

print('Profile picker tests passed: ' .. total)
