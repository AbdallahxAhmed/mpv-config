-- ytdl-sub-menu.lua: On-demand YouTube auto-subtitles & dubs menu integrated with uosc
local utils = require 'mp.utils'
local msg = require 'mp.msg'

local is_fetching = false

local function find_ytdl_path()
    local opt_path = mp.get_opt("ytdl_hook-ytdl_path") or mp.get_opt("ytdl_path")
    if opt_path and opt_path ~= "" and utils.file_info(opt_path) then
        return opt_path
    end

    local candidate_paths = {
        "C:/Program Files/mpv/yt-dlp/yt-dlp.exe",
        "C:/Program Files/mpv/yt-dlp.exe",
        "C:/Program Files/mpv/yt-dlp/yt-dlp",
        "yt-dlp",
    }
    for _, path in ipairs(candidate_paths) do
        if utils.file_info(path) then
            return path
        end
    end

    return "yt-dlp"
end

local function get_youtube_url()
    local path = mp.get_property("path", "")
    if path:find("youtube%.com/") or path:find("youtu%.be/") then
        return path
    end
    if path:find("^ytdl://") then
        return path:sub(8)
    end
    return nil
end

local function fetch_subtitle(lang)
    if is_fetching then
        mp.osd_message("جاري تنزيل ترجمة أخرى حالياً...", 2)
        return
    end

    local url = get_youtube_url()
    if not url then
        mp.osd_message("خطأ: المقطع الحالي ليس من يوتيوب", 3)
        return
    end

    is_fetching = true
    mp.osd_message("جاري تنزيل الترجمة التلقائية...", 4)

    local ytdl = find_ytdl_path()
    local temp_dir = os.getenv("TEMP") or os.getenv("TMP") or "."
    local timestamp = os.time()
    local out_template = temp_dir .. "/mpv_ytdl_sub_" .. timestamp .. "_%(id)s.%(ext)s"

    local args = {
        ytdl,
        "--skip-download",
        "--write-auto-subs",
        "--write-subs",
        "--sub-langs", lang .. ".*," .. lang,
        "--sub-format", "vtt/best",
        "--no-playlist",
        "-o", out_template,
        url,
    }

    mp.command_native_async({
        name = "subprocess",
        playback_only = false,
        capture_stdout = true,
        capture_stderr = true,
        args = args,
    }, function(success, res, err)
        is_fetching = false
        if not success or not res or res.status ~= 0 then
            msg.error("yt-dlp sub fetch failed: " .. tostring(err or (res and res.stderr)))
            mp.osd_message("فشل تنزيل الترجمة التلقائية", 3)
            return
        end

        local sub_file = nil
        local stdout = res.stdout or ""

        local found = stdout:match("Destination:%s*([^\r\n]+)") or stdout:match("Writing video subtitles to:%s*([^\r\n]+)")
        if found then
            found = found:gsub('^"', ''):gsub('"$', ''):gsub('^%s+', ''):gsub('%s+$', '')
            if utils.file_info(found) then
                sub_file = found
            end
        end

        if not sub_file then
            local expected_prefix = temp_dir .. "/mpv_ytdl_sub_" .. timestamp .. "_"
            for _, suffix in ipairs({
                "." .. lang .. ".vtt",
                ".vtt",
                "." .. lang .. ".srt",
                ".srt",
            }) do
                local check_path = expected_prefix .. suffix
                if utils.file_info(check_path) then
                    sub_file = check_path
                    break
                end
            end
        end

        if sub_file and utils.file_info(sub_file) then
            local lang_title = "YouTube Auto (" .. lang:upper() .. ")"
            mp.commandv("sub-add", sub_file, "select", lang_title, lang)
            mp.osd_message("✓ تم تفعيل الترجمة التلقائية (" .. lang .. ")", 3)
            msg.info("Loaded subtitle: " .. sub_file)
        else
            mp.osd_message("لم يتم العثور على ترجمة لهذه اللغة", 3)
            msg.warn("No subtitle file found for " .. lang .. ". stdout: " .. stdout)
        end
    end)
end

local function open_sub_menu()
    local path = mp.get_property("path", "")
    if path == "" then
        mp.osd_message("لا يوجد ملف قيد التشغيل", 2)
        return
    end

    local track_list = mp.get_property_native("track-list", {})
    local current_sid = mp.get_property_native("sid")
    local items = {}

    -- Option to disable subtitles
    table.insert(items, {
        title = "إيقاف الترجمة (Off)",
        hint = "none",
        icon = "subtitles_off",
        active = (current_sid == false or current_sid == 0 or current_sid == nil),
        value = "set sid no",
    })

    -- Existing loaded tracks
    for _, track in ipairs(track_list) do
        if track.type == "sub" then
            local title = track.title or track.lang or ("Track " .. tostring(track.id))
            local hint_parts = {}
            if track.lang and track.lang ~= "" then
                table.insert(hint_parts, track.lang:upper())
            end
            if track["external"] then
                table.insert(hint_parts, "external")
            end
            if track["forced"] then
                table.insert(hint_parts, "forced")
            end
            if track["default"] then
                table.insert(hint_parts, "default")
            end

            table.insert(items, {
                title = title,
                hint = table.concat(hint_parts, ", "),
                icon = "subtitles",
                active = (track.id == current_sid),
                value = "set sid " .. tostring(track.id),
            })
        end
    end

    -- YouTube auto-subtitles section
    local is_youtube = get_youtube_url() ~= nil
    if is_youtube then
        table.insert(items, {
            separator = true,
            title = "YouTube Auto Subtitles",
        })

        table.insert(items, {
            title = "📥 جلب ترجمة تلقائية (العربية)",
            hint = "Arabic Auto-sub",
            icon = "cloud_download",
            value = "script-message-to ytdl_sub_menu fetch-sub ar",
        })

        table.insert(items, {
            title = "📥 جلب ترجمة تلقائية (الإنجليزية)",
            hint = "English Auto-sub",
            icon = "cloud_download",
            value = "script-message-to ytdl_sub_menu fetch-sub en",
        })

        local other_langs = {
            { code = "fr", name = "الفرنسية (French)" },
            { code = "es", name = "الإسبانية (Spanish)" },
            { code = "de", name = "الألمانية (German)" },
            { code = "tr", name = "التركية (Turkish)" },
            { code = "ja", name = "اليابانية (Japanese)" },
            { code = "ko", name = "الكورية (Korean)" },
            { code = "ru", name = "الروسية (Russian)" },
            { code = "it", name = "الإيطالية (Italian)" },
            { code = "pt", name = "البرتغالية (Portuguese)" },
            { code = "id", name = "الإندونيسية (Indonesian)" },
            { code = "ur", name = "الأردية (Urdu)" },
            { code = "hi", name = "الهندية (Hindi)" },
        }

        local sub_items = {}
        for _, l in ipairs(other_langs) do
            table.insert(sub_items, {
                title = l.name,
                hint = l.code:upper(),
                icon = "translate",
                value = "script-message-to ytdl_sub_menu fetch-sub " .. l.code,
            })
        end

        table.insert(items, {
            title = "🌐 جلب لغة أخرى...",
            icon = "language",
            items = sub_items,
        })
    end

    local menu_data = {
        type = "ytdl_sub_menu",
        title = "الترجمة والمسارات (Subtitles)",
        items = items,
    }

    mp.commandv("script-message-to", "uosc", "open-menu", utils.format_json(menu_data))
end

mp.add_key_binding(nil, "open", open_sub_menu)
mp.register_script_message("open", open_sub_menu)
mp.register_script_message("open-menu", open_sub_menu)
mp.register_script_message("fetch-sub", fetch_subtitle)
