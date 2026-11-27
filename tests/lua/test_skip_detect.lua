-- skip_detect: which chapters SmartSkip treats as intro / outro / preview.
local total = 0
local function eq(a, b, what)
    assert(a == b, (what and (what .. ': ') or '') .. tostring(a) .. ' ~= ' .. tostring(b))
end
local function test(name, fn) fn(); total = total + 1; print('ok skip_detect: ' .. name) end

local here = debug.getinfo(1, 'S').source:sub(2)
here = (here:match('^(.*)[/\\][^/\\]*$') or '.') .. '/'
local D = dofile(here .. '../../scripts/modules/skip_detect.lua')

-- chapter list from {start_seconds, title} pairs
local function chapters(spec)
    local list = {}
    for i, c in ipairs(spec) do list[i] = { time = c[1], title = c[2] } end
    return list
end

local EP = 24 * 60 -- a 24-minute episode

test('opening names in any case and spelling', function()
    for _, t in ipairs({ 'Opening', 'opening', 'OPENING', 'OP', 'Op', 'op', 'OP1', 'OP 2',
        'NCOP', 'OP - Kaikai Kitan', 'OP: Gurenge', 'Opening Credits', 'Opening Theme',
        'Theme Song', 'Title Sequence', 'op_start', 'OP Start' }) do
        eq(D.name_category(t), 'opening', t)
    end
end)

test('ending names in any case and spelling', function()
    for _, t in ipairs({ 'Ending', 'ending', 'ED', 'Ed', 'ED2', 'NCED', 'ED - Shirushi',
        'End Credits', 'Credits', 'Outro', 'Credits Start', 'Ending Theme', 'Staff Roll',
        'Part B ED' }) do
        eq(D.name_category(t), 'ending', t)
    end
end)

test('preview, recap and prologue names', function()
    eq(D.name_category('Preview'), 'preview')
    eq(D.name_category('Next Episode Preview'), 'preview')
    eq(D.name_category('Next Episode'), 'preview')
    eq(D.name_category('Next Time'), 'preview')
    eq(D.name_category('Recap'), 'recap')
    eq(D.name_category('Previously On'), 'recap')
    eq(D.name_category('Prologue'), 'prologue')
    eq(D.name_category('Avant'), 'prologue')
    eq(D.name_category('Cold Open'), 'prologue')
end)

test('Japanese and Arabic names', function()
    eq(D.name_category('オープニング'), 'opening')
    eq(D.name_category('エンディング'), 'ending')
    eq(D.name_category('次回予告'), 'preview')
    eq(D.name_category('شارة البداية'), 'opening')
    eq(D.name_category('تتر النهاية'), 'ending')
    eq(D.name_category('الحلقة القادمة'), 'preview')
end)

test('content that only looks like an intro or outro is never tagged', function()
    for _, t in ipairs({ 'Operation Meteor', 'Edward', 'Ed and Al', 'Opera House',
        'Post-Credits Scene', 'After Credits', 'Mid-Credits', 'Alternate Ending',
        'Ending Scene', 'True Ending', 'Opening Scene', 'Part A', 'Part B', 'Episode',
        'Introduction', 'Eyecatch', 'Chapter 3' }) do
        eq(D.name_category(t), nil, t)
    end
end)

test('generic chapter names', function()
    for _, t in ipairs({ '', 'Chapter 1', 'chapter 12', 'Chapter', 'Ch. 4', '01', '00:01:30.000',
        'Kapitel 2', 'Chapitre 3', 'Capítulo 5', 'الفصل 2', 'チャプター 3' }) do
        eq(D.is_generic(t), true, t)
    end
    eq(D.is_generic(nil), true, 'nil')
    for _, t in ipairs({ 'Part A', 'Opening', 'Prologue', 'Eyecatch' }) do
        eq(D.is_generic(t), false, t)
    end
end)

test('named list: lowercase names that the stock patterns miss', function()
    local r = D.classify(chapters({
        { 0, 'prologue' }, { 150, 'opening' }, { 240, 'part a' }, { 800, 'part b' },
        { 1320, 'ending' }, { 1410, 'preview' },
    }), EP)
    eq(r.categories[1], 'prologue')
    eq(r.categories[2], 'opening')
    eq(r.categories[3], nil)
    eq(r.categories[5], 'ending')
    eq(r.categories[6], 'preview')
    eq(r.sources[2], 'name')
end)

test('"Intro" is the opening when nothing else is', function()
    local r = D.classify(chapters({
        { 0, 'Intro' }, { 60, 'Episode' }, { 1300, 'Credits' },
    }), 1400)
    eq(r.categories[1], 'opening')
    eq(r.categories[3], 'ending')
end)

test('"Intro" is the cold open when an OP chapter exists', function()
    local r = D.classify(chapters({
        { 0, 'Intro' }, { 70, 'OP' }, { 160, 'Episode' }, { 1320, 'ED' },
    }), EP)
    eq(r.categories[1], 'prologue')
    eq(r.categories[2], 'opening')
end)

test('a long "Intro" is a cold open, not a title sequence', function()
    local r = D.classify(chapters({ { 0, 'Intro' }, { 300, 'Episode' } }), EP)
    eq(r.categories[1], 'prologue')
end)

test('unnamed BD chapters: OP and ED found by their ~1:30 length', function()
    local r = D.classify(chapters({
        { 0, 'Chapter 1' },        -- cold open 2:05
        { 125, 'Chapter 2' },      -- OP 1:30
        { 215, 'Chapter 3' },      -- part A
        { 760, 'Chapter 4' },      -- part B
        { 1305, 'Chapter 5' },     -- ED 1:30
        { 1395, 'Chapter 6' },     -- preview 0:15
    }), 1410)
    eq(r.categories[1], nil)
    eq(r.categories[2], 'opening')
    eq(r.sources[2], 'length')
    eq(r.categories[3], nil)
    eq(r.categories[4], nil)
    eq(r.categories[5], 'ending')
    eq(r.categories[6], 'preview')
end)

test('unnamed chapters: song-length cold open right before the OP', function()
    local r = D.classify(chapters({
        { 0, '' }, { 90, '' }, { 180, '' }, { 760, '' }, { 1320, '' },
    }), 1410)
    eq(r.categories[1], nil, 'cold open')
    eq(r.categories[2], 'opening')
    eq(r.categories[5], 'ending')
end)

test('unnamed chapters: ED followed by a song-length C-part', function()
    local r = D.classify(chapters({
        { 0, '' }, { 90, '' }, { 700, '' }, { 1230, '' }, { 1320, '' },
    }), 1410)
    eq(r.categories[1], 'opening')
    eq(r.categories[4], 'ending')
    eq(r.categories[5], nil, 'C-part')
end)

test('a stinger after the ending is not a preview when it is long', function()
    local r = D.classify(chapters({
        { 0, '' }, { 90, '' }, { 700, '' }, { 1250, '' }, { 1340, '' },
    }), 1440)
    eq(r.categories[4], 'ending')
    eq(r.categories[5], nil)
end)

test('timestamps as names count as unnamed', function()
    local r = D.classify(chapters({
        { 0, '00:00:00.000' }, { 90, '00:01:30.000' }, { 700, '00:11:40.000' },
        { 1320, '00:22:00.000' },
    }), 1410)
    eq(r.categories[1], 'opening')
    eq(r.categories[4], 'ending')
end)

test('length guessing stays off for movies and short clips', function()
    local spec = chapters({ { 0, '' }, { 90, '' }, { 600, '' }, { 5900, '' } })
    local r = D.classify(spec, 6000)
    eq(next(r.categories), nil, 'movie')
    r = D.classify(chapters({ { 0, '' }, { 90, '' }, { 180, '' } }), 300)
    eq(next(r.categories), nil, 'short clip')
end)

test('length guessing stays off when the names already say where OP/ED are', function()
    local r = D.classify(chapters({
        { 0, 'Chapter 1' }, { 90, 'Chapter 2' }, { 700, 'Chapter 3' }, { 1320, 'Ending' },
    }), 1410)
    eq(r.categories[1], nil)
    eq(r.categories[4], 'ending')
end)

test('length guessing never relabels named content', function()
    local r = D.classify(chapters({
        { 0, 'Part A' }, { 90, 'Part B' }, { 700, 'Part C' }, { 1320, 'Part D' },
    }), 1410)
    eq(next(r.categories), nil)
end)

test('evenly cut chapters carry no structure', function()
    local spec = {}
    for i = 0, 15 do spec[#spec + 1] = { i * 90, '' } end
    local r = D.classify(chapters(spec), 1440)
    eq(next(r.categories), nil)
end)

test('heuristics can be switched off', function()
    local r = D.classify(chapters({
        { 0, '' }, { 90, '' }, { 700, '' }, { 1320, '' },
    }), 1410, { heuristics = false })
    eq(next(r.categories), nil)
end)

test('describe() gives a sorted log line', function()
    local r = D.classify(chapters({
        { 0, 'Chapter 1' }, { 125, 'Chapter 2' }, { 215, 'Chapter 3' }, { 760, 'Chapter 4' },
        { 1305, 'Chapter 5' }, { 1395, 'Chapter 6' },
    }), 1410)
    eq(D.describe(r), '2=opening(length) 5=ending(length) 6=preview(length)')
end)

print('skip_detect tests passed: ' .. total)
