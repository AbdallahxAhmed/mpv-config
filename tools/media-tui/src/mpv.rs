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

use crate::bridge::find_repo_root;

pub fn download_item(result: &SearchResult) -> std::io::Result<Child> {
    let dl_url = result.download_url.as_ref().unwrap_or(&result.url);
    let downloads_dir = std::env::var("USERPROFILE")
        .map(|p| format!("{}\\Downloads", p))
        .unwrap_or_else(|_| ".".to_string());

    let repo_root = find_repo_root();
    let script = repo_root.join("tools").join("universal_downloader.py");

    let clean_title = result.title.replace(['"', '\'', '`', '\\', '/'], "");

    // Determine site-specific referer if needed
    let referer = if result.provider == "HentaiMama" {
        Some("https://hentaimama.io/")
    } else if result.provider == "MuchoHentai" {
        Some("https://muchohentai.com/")
    } else if result.provider == "Hanime" {
        Some("https://hanime.tv/")
    } else {
        None
    };

    if result.delivery == "Torrent (P2P)" || dl_url.ends_with(".torrent") || dl_url.starts_with("magnet:") {
        // Spawn aria2c in a separate window so user sees progress
        Command::new("cmd")
            .args([
                "/c",
                "start",
                &format!("Torrent Turbo Download - {}", clean_title),
                "aria2c",
                dl_url,
                &format!("--dir={}", downloads_dir),
                "--seed-time=0",
                "--max-connection-per-server=16",
                "--split=16",
            ])
            .spawn()
    } else if let Some(ref_url) = referer {
        // Direct yt-dlp with aria2c turbo downloader and referer header in a separate window
        Command::new("cmd")
            .args([
                "/c",
                "start",
                &format!("Turbo Download - {}", clean_title),
                "yt-dlp",
                "--downloader",
                "aria2c",
                "--downloader-args",
                "aria2c:-s 16 -x 16 -k 1M",
                "--add-header",
                &format!("Referer: {}", ref_url),
                "-P",
                &downloads_dir,
                dl_url,
            ])
            .spawn()
    } else {
        // Use universal_downloader.py with absolute path in a separate window
        Command::new("cmd")
            .args([
                "/c",
                "start",
                &format!("Turbo Download - {}", clean_title),
                "python",
                script.to_str().unwrap_or("tools/universal_downloader.py"),
                dl_url,
                "-o",
                &downloads_dir,
            ])
            .current_dir(&repo_root)
            .spawn()
    }
}

pub fn copy_to_clipboard(text: &str) {
    let _ = Command::new("powershell")
        .args(["-NoProfile", "-Command", &format!("Set-Clipboard -Value '{}'", text.replace('\'', "''"))])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();
}
