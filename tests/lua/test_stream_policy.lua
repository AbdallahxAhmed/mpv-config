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
test('malformed metadata is ignored',function()
    eq(#p.captions(nil),0)
    eq(#p.captions({subtitles=false,automatic_captions={en=false,ar={false,{ext='vtt'}}}}),0)
end)
print('Policy tests passed: '..n)
