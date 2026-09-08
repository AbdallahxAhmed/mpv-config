local p = dofile('scripts/modules/stream_policy.lua')
local n = 0
local function test(name, fn) fn(); n=n+1; print('ok policy: '..name) end
local function eq(a,b) assert(a==b, tostring(a)..' ~= '..tostring(b)) end
local function audio(id,lang,rate,note)
    return {format_id=id, language=lang, abr=rate, format_note=note,
        acodec='opus', vcodec='none', url='https://media.example/'..id}
end
local video={format_id='v',acodec='none',vcodec='avc1',url='https://media.example/v'}
local function filter(f,j) return p.best_audio_formats(j or {extractor='youtube',duration=100},f) end
test('strict hosts',function()
    assert(p.youtube_url('ytdl://https://youtu.be/abc'))
    assert(p.youtube_url('https://m.youtube.com/shorts/abc'))
    for _,u in ipairs({'https://youtube.com.evil.test/a','https://evil.test/?u=youtube.com/a',
        'https://youtube.com@evil.test/a','/media/youtube.com/a','ytdl://https://evil.test/a',
        'file:///tmp/a','https://youtube.com/a\n--exec=bad'}) do eq(p.youtube_url(u),nil) end
end)
test('highest bitrate and default language remap',function()
    local low,high,en=audio('ar-low','ar',64,'low'),audio('ar-high','ar',256,'high'),audio('en','en',128,'medium')
    local f,r=filter({video,low,en,high})
    eq(#f,3); eq(f[1],video); eq(f[2],en); eq(f[3],high); eq(r['ar-low'],'ar-high')
    eq(low.format_id,'ar-low')
end)
test('distinct roles dialects DRC and commentary survive',function()
    local f={video}
    for i,v in ipairs({{'en','original'},{'en','dubbed'},{'en-desc','descriptive'},
        {'en','DRC'},{'pt-BR','medium'},{'pt-PT','medium'},{'en','commentary'}}) do
        f[#f+1]=audio(tostring(i),v[1],128,v[2])
    end
    eq(#filter(f),#f)
end)
test('unknown metadata and muxed video survive',function()
    local mux=audio('mux','en',128); mux.vcodec='avc1'
    local f={video,mux,audio('a',nil,300),audio('b',nil,64),audio('c','en',nil),audio('d','en',200)}
    eq(#filter(f),#f)
end)
test('live non-YouTube and audio-only remain untouched',function()
    local f={video,audio('a','en',64),audio('b','en',256)}
    eq(filter(f,{extractor='youtube',is_live=true}),f); eq(filter(f,{extractor='twitch'}),f)
    local a={f[2],f[3]}; eq(filter(a),a)
end)
test('numeric bitrate fallbacks and stable ties',function()
    local a,b,c=audio('a','en',nil),audio('b','en',nil),audio('c','en',256)
    a.tbr='128'; b.filesize=3200000
    local f=filter({video,a,b,c}); eq(#f,2); eq(f[2],c); eq(p.audio_bitrate(b,100),256)
end)
test('unsafe or DRM cannot replace playable rendition',function()
    local bad,good=audio('bad','en',999),audio('good','en',128)
    bad.url='file:///etc/passwd'; eq(#filter({video,bad,good}),3)
    bad.url='https://media.example/bad'; bad.has_drm=true; eq(#filter({video,bad,good}),3)
end)
test('explicit subtitle requests override lazy default',function()
    assert(p.lazy_subtitles('https://youtu.be/abc',{}))
    for _,k in ipairs({'write-subs','write-auto-subs','sub-langs','no-write-subs'}) do
        assert(not p.lazy_subtitles('https://youtu.be/abc',{[k]=''}))
    end
    assert(not p.lazy_subtitles('https://other.example/a',{}))
end)
test('creator generated translated and unsupported formats',function()
    local f=p.captions({subtitles={ar={{ext='json3',url='https://yt.example/json'},
        {ext='vtt',url='https://yt.example/ar',name='Arabic'}},live_chat={{ext='vtt',url='https://yt.example/chat'}}},
        automatic_captions={['en-orig']={{ext='vtt',url='https://yt.example/en'}},
        fr={{ext='vtt',url='https://yt.example/c?tlang=fr'}},bad={{ext='vtt',url='file:///etc/passwd'}}}},'ar,en')
    eq(#f,3); eq(f[1].lang,'ar'); eq(f[1].kind,'manual'); eq(f[2].lang,'en')
    eq(f[2].kind,'automatic'); eq(f[3].kind,'translated')
end)
test('creator first and normalized language preference',function()
    local f=p.captions({subtitles={en={{ext='srt',url='https://yt.example/manual'}}},
        automatic_captions={en={{ext='vtt',url='https://yt.example/auto'}}}},{'en'})
    eq(p.preferred_caption(f,'eng').kind,'manual'); eq(p.preferred_caption(f,'ar'),nil)
    eq(p.language('jpn'),'ja'); eq(p.language('pt_BR'),'pt-br')
end)
test('prune null codec and multilingual duplicate audio tracks',function()
    local aac_ar = audio('140-1','ar',128,'Arabic original (default), medium')
    local null_ar1 = {format_id='234-1',language='ar',acodec='none',vcodec='none',format_note='العربية - original (original)',url='https://media.example/234-1'}
    local null_ar2 = {format_id='233-1',language='ar',acodec='none',vcodec='none',format_note='العربية - original (original)',url='https://media.example/233-1'}
    local aac_ja = audio('140-0','ja',128,'Japanese, medium')
    local null_ja = {format_id='234-0',language='ja',acodec='none',vcodec='none',format_note='日本語 - dubbed',url='https://media.example/234-0'}
    local f, r = filter({video, aac_ar, null_ar1, null_ar2, aac_ja, null_ja})
    eq(#f, 3)
    eq(f[1], video)
    eq(f[2], aac_ar)
    eq(f[3], aac_ja)
    eq(r['234-1'], '140-1')
    eq(r['233-1'], '140-1')
    eq(r['234-0'], '140-0')
end)
test('auto-generated captions deduplicate orig and non-orig variants',function()
    local f = p.captions({automatic_captions={
        ar={{ext='vtt',name='Arabic',url='https://yt.example/ar'}},
        ['ar-orig']={{ext='vtt',name='Arabic (Original)',url='https://yt.example/ar-orig'}}
    }},'ar')
    eq(#f, 1)
    eq(f[1].lang, 'ar')
    eq(f[1].name, 'Arabic')
    eq(f[1].kind, 'automatic')
end)
test('malformed metadata is ignored',function()
    eq(#p.captions(nil),0)
    eq(#p.captions({subtitles=false,automatic_captions={en=false,ar={false,{ext='vtt'}}}}),0)
end)
test('ISO normalization and audio title fallback monogram',function()
    eq(p.monogram('ara', nil), 'AR')
    eq(p.monogram('eng', nil), 'EN')
    eq(p.monogram('jpn', nil), 'JA')
    eq(p.monogram('deu', nil), 'DE')
    eq(p.monogram('ger', nil), 'DE')
    eq(p.monogram('fra', nil), 'FR')
    eq(p.monogram('ar', nil), 'AR')
    eq(p.monogram('en', nil), 'EN')
    eq(p.monogram('und', '[ENG] Dual-Audio'), 'EN')
    eq(p.monogram('', 'Arabic Dub'), 'AR')
    eq(p.monogram(nil, 'Japanese Original'), 'JA')
    eq(p.monogram(nil, 'Unknown Audio Track'), nil)
    eq(p.monogram('xyz', nil), 'XY')
end)
test('widescreen and ultrawide quality monogram detection',function()
    eq(p.quality_monogram(1920, 800), 'HD')
    eq(p.quality_monogram(3840, 1600), '4K')
    eq(p.quality_monogram(640, 360), 'SD')
    eq(p.quality_monogram(1920, 1080), 'HD')
    eq(p.quality_monogram(3840, 2160), '4K')
    eq(p.quality_monogram(2560, 1440), 'HD')
    eq(p.quality_monogram(1080, 1920), 'HD')
    eq(p.quality_monogram(0, 0), nil)
end)
test('caption primary flag distinguishes ar and en from other languages',function()
    local f = p.captions({automatic_captions={
        ar={{ext='vtt',name='Arabic',url='https://yt.example/ar'}},
        en={{ext='vtt',name='English',url='https://yt.example/en'}},
        fr={{ext='vtt',name='French',url='https://yt.example/fr?tlang=fr'}},
        de={{ext='vtt',name='German',url='https://yt.example/de?tlang=de'}}
    }},'ar,en')
    local by_lang = {}
    for _, c in ipairs(f) do by_lang[c.lang] = c end
    assert(by_lang['ar'] and by_lang['ar'].is_primary == true)
    assert(by_lang['en'] and by_lang['en'].is_primary == true)
    assert(by_lang['fr'] and by_lang['fr'].is_primary == false)
    assert(by_lang['de'] and by_lang['de'].is_primary == false)
end)
test('stream quality label maps cinema, ultrawide, vertical and standard streams',function()
    eq(p.quality_label(1920, 960, 24, '1080p'), '1080p')
    eq(p.quality_label(2560, 1280, 24, '1440p'), '1440p')
    eq(p.quality_label(3840, 1920, 24, '2160p'), '4K (2160p)')
    eq(p.quality_label(1280, 640, 24, '720p'), '720p')
    eq(p.quality_label(854, 428, 24, '480p'), '480p')
    eq(p.quality_label(640, 320, 24, '360p'), '360p')
    eq(p.quality_label(1920, 960, nil, nil), '1080p')
    eq(p.quality_label(1920, 1080, 60, nil), '1080p60')
    eq(p.quality_label(1280, 720, 30, nil), '720p')
    eq(p.quality_label(1080, 1920, 30, '1080p'), '1080p')
    eq(p.quality_label(720, 1280, 30, '720p'), '720p')
end)
test('default download dir resolves to Downloads', function()
    local dir = p.default_download_dir()
    assert(type(dir) == 'string')
    assert(dir:find('Downloads') ~= nil)
end)
test('download args builds valid yt-dlp arguments for video and audio', function()
    local video_args = p.download_args('https://www.youtube.com/watch?v=abc', 'D:/Videos', false, 'bestvideo[height<=?1080]+bestaudio/best')
    eq(video_args[1], 'yt-dlp')
    assert(table.concat(video_args, ' '):find('--continue', 1, true))
    assert(table.concat(video_args, ' '):find('--no-overwrites', 1, true))
    assert(table.concat(video_args, ' '):find('--concurrent-fragments 4', 1, true))
    assert(table.concat(video_args, ' '):find('--merge-output-format mp4', 1, true))
    eq(video_args[#video_args], 'https://www.youtube.com/watch?v=abc')

    local audio_args = p.download_args('https://www.youtube.com/watch?v=abc', 'D:/Music', true)
    assert(table.concat(audio_args, ' '):find('-x', 1, true))
    assert(table.concat(audio_args, ' '):find('--audio-format mp3', 1, true))
    eq(audio_args[#audio_args], 'https://www.youtube.com/watch?v=abc')

    eq(p.download_args(nil), nil)
    eq(p.download_args(''), nil)
end)
test('analyze cache coverage accurately identifies complete and partial ranges', function()
    local cov1 = p.analyze_cache_coverage({['seekable-ranges'] = {{start = 0, ['end'] = 100}}}, 100)
    eq(cov1.is_complete, true)
    eq(cov1.coverage_pct, 100)
    eq(cov1.start_time, 0)
    eq(cov1.end_time, 100)

    local cov2 = p.analyze_cache_coverage({['seekable-ranges'] = {{start = 1, ['end'] = 99}}}, 100)
    eq(cov2.is_complete, true)
    eq(cov2.coverage_pct, 98)

    local cov3 = p.analyze_cache_coverage({['seekable-ranges'] = {{start = 0, ['end'] = 30}}}, 100)
    eq(cov3.is_complete, false)
    eq(cov3.coverage_pct, 30)

    local cov4 = p.analyze_cache_coverage({['seekable-ranges'] = {{start = 0, ['end'] = 45}, {start = 50, ['end'] = 98}}}, 100)
    eq(cov4.is_complete, true)
    eq(cov4.coverage_pct, 93)

    local cov5 = p.analyze_cache_coverage(nil, 100)
    eq(cov5.is_complete, false)
    eq(cov5.coverage_pct, 0)

    local cov6 = p.analyze_cache_coverage({['seekable-ranges'] = {}}, 0)
    eq(cov6.is_complete, false)
    eq(cov6.coverage_pct, 0)
end)
test('resolve download target path sanitizes title and preserves directory', function()
    local path1 = p.resolve_download_target_path('Cool Video: Part 1 / 2? *special*', 'D:/Downloads', 'mp4')
    eq(path1, 'D:/Downloads/Cool Video_ Part 1 _ 2_ _special_.mp4')

    local path2 = p.resolve_download_target_path('', nil, 'mkv')
    assert(path2:find('/Downloads/video.mkv') ~= nil)

    local mock_files = {['D:/Downloads/video.mp4'] = true, ['D:/Downloads/video (1).mp4'] = true}
    local path3 = p.resolve_download_target_path('video', 'D:/Downloads', 'mp4', function(p) return mock_files[p] == true end)
    eq(path3, 'D:/Downloads/video (2).mp4')
end)
test('clean stream url normalizes quotes whitespace and edl protocols', function()
    eq(p.clean_stream_url('""https://txxx.com/videos/17007267/""'), 'https://txxx.com/videos/17007267/')
    eq(p.clean_stream_url('  \'https://vimeo.com/12345\'  '), 'https://vimeo.com/12345')
    eq(p.clean_stream_url('ytdl://https://youtu.be/abc'), 'https://youtu.be/abc')
    local edl = 'edl://!new_stream;%44%https://site.com/get_file/video.mp4?ti=123,length=120'
    eq(p.clean_stream_url(edl), 'https://site.com/get_file/video.mp4?ti=123')
    eq(p.clean_stream_url('C:\\movies\\local.mp4'), nil)
    eq(p.clean_stream_url(nil), nil)
end)
test('resolve stream urls returns primary extractor URL and secondary direct stream', function()
    local source = '""https://txxx.com/videos/17007267/""'
    local edl = 'edl://!new_stream;%44%https://site.com/get_file/video.mp4?ti=123,length=120'
    local pri, sec = p.resolve_stream_urls(source, edl, nil)
    eq(pri, 'https://txxx.com/videos/17007267/')
    eq(sec, 'https://site.com/get_file/video.mp4?ti=123')

    local pri2, sec2 = p.resolve_stream_urls(nil, 'https://youtu.be/123', nil)
    eq(pri2, 'https://youtu.be/123')
    eq(sec2, nil)
end)
test('download args supports no-mtime referer and custom user-agent', function()
    local args = p.download_args('https://site.com/video', 'D:/Downloads', false, nil, {
        referer = 'https://site.com/',
        user_agent = 'Mozilla/5.0 CustomAgent/1.0',
    })
    local full = table.concat(args, ' ')
    assert(full:find('--no-mtime', 1, true) ~= nil)
    assert(full:find('--referer https://site.com/', 1, true) ~= nil)
    assert(full:find('--user-agent Mozilla/5.0 CustomAgent/1.0', 1, true) ~= nil)
end)
print('Policy tests passed: '..n)
