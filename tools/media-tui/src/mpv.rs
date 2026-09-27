use std::process::{Child, Command, Stdio};
use std::path::Path;
use crate::models::SearchResult;

pub fn find_mpv() -> String {
    let candidates = [
        "mpv",
        r"C:\Program Files\mpv\mpv.exe",
        r"C:\Program Files\mpv\mpv.com",
    ];

    for c in &candidates {
        if Path::new(c).is_file() {
            return c.to_string();
        }
    }
    "mpv".to_string()
}

pub fn play_in_mpv(result: &SearchResult) -> std::io::Result<Child> {
    let mpv = find_mpv();
    let mut cmd = Command::new(mpv);

    cmd.arg("--force-window=yes")
        .arg(format!("--title=🎬 Play: {}", result.title))
        .arg(&result.url);

    if result.provider == "HentaiMama" {
        cmd.arg("--http-header-fields=Referer: https://hentaimama.io/");
    } else if result.provider == "Hanime" {
        cmd.arg("--http-header-fields=Referer: https://hanime.tv/");
    } else if result.provider == "MuchoHentai" {
        cmd.arg("--http-header-fields=Referer: https://muchohentai.com/");
    }

    cmd.spawn()
}

pub fn preview_floating(result: &SearchResult) -> std::io::Result<Child> {
    let mpv = find_mpv();
    let mut cmd = Command::new(mpv);

    let target = if result.delivery != "Torrent (P2P)" {
        &result.url
    } else {
        result.thumbnail.as_ref().unwrap_or(&result.url)
    };

    cmd.arg("--geometry=520x290-30-30")
        .arg("--ontop")
        .arg("--no-border")
        .arg("--autofit=520x290")
        .arg(format!("--title=👁 Preview: {}", result.title))
        .arg(target);

    if result.provider == "HentaiMama" {
        cmd.arg("--http-header-fields=Referer: https://hentaimama.io/");
    } else if result.provider == "Hanime" {
        cmd.arg("--http-header-fields=Referer: https://hanime.tv/");
    } else if result.provider == "MuchoHentai" {
        cmd.arg("--http-header-fields=Referer: https://muchohentai.com/");
    }

    cmd.spawn()
}

pub fn download_item(result: &SearchResult) -> std::io::Result<Child> {
    let dl_url = result.download_url.as_ref().unwrap_or(&result.url);
    let downloads_dir = std::env::var("USERPROFILE")
        .map(|p| format!("{}\\Downloads", p))
        .unwrap_or_else(|_| ".".to_string());

    if result.delivery == "Torrent (P2P)" || dl_url.ends_with(".torrent") || dl_url.starts_with("magnet:") {
        // Try aria2c
        let mut cmd = Command::new("aria2c");
        cmd.arg(dl_url)
            .arg(format!("--dir={}", downloads_dir))
            .arg("--seed-time=0")
            .arg("--max-connection-per-server=16")
            .arg("--split=16");

        if let Ok(child) = cmd.spawn() {
            return Ok(child);
        }
    }

    // Default to universal downloader / yt-dlp
    let mut cmd = Command::new("python");
    cmd.arg("tools/universal_downloader.py")
        .arg(dl_url)
        .current_dir(downloads_dir);

    cmd.spawn()
}

pub fn copy_to_clipboard(text: &str) {
    let _ = Command::new("powershell")
        .args(["-NoProfile", "-Command", &format!("Set-Clipboard -Value '{}'", text.replace('\'', "''"))])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();
}
