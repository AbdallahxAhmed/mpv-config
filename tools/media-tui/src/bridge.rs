use std::path::PathBuf;
use tokio::process::Command;
use crate::models::{BridgeResponse, SearchResult};
use anyhow::{Result, Context};

fn find_repo_root() -> PathBuf {
    // 1. Walk up from CWD
    if let Ok(cwd) = std::env::current_dir() {
        let mut curr = cwd;
        for _ in 0..8 {
            if curr.join("tools").join("search").join("json_bridge.py").exists() {
                return curr;
            }
            if !curr.pop() {
                break;
            }
        }
    }
    // 2. Walk up from current exe location
    if let Ok(exe) = std::env::current_exe() {
        let mut curr = exe;
        for _ in 0..8 {
            if curr.join("tools").join("search").join("json_bridge.py").exists() {
                return curr;
            }
            if !curr.pop() {
                break;
            }
        }
    }
    PathBuf::from(".")
}

pub async fn run_search_bridge(query: &str) -> Result<Vec<SearchResult>> {
    let repo_root = find_repo_root();
    let script = repo_root.join("tools").join("search").join("json_bridge.py");

    let output = Command::new("python")
        .current_dir(&repo_root)
        .arg(&script)
        .arg(query)
        .output()
        .await
        .context("Failed to spawn python json_bridge")?;

    if !output.status.success() {
        let err_msg = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!("Bridge error: {}", err_msg);
    }

    let resp: BridgeResponse = serde_json::from_slice(&output.stdout)
        .context("Failed to parse json_bridge output")?;

    Ok(resp.results)
}

pub async fn download_image_to_cache(url: &str) -> Option<PathBuf> {
    let repo_root = find_repo_root();
    let script = repo_root.join("tools").join("search").join("fetch_image.py");

    let output = Command::new("python")
        .current_dir(&repo_root)
        .arg(&script)
        .arg(url)
        .output()
        .await
        .ok()?;

    if output.status.success() {
        let path_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if !path_str.is_empty() {
            let path = PathBuf::from(path_str);
            if path.exists() {
                return Some(path);
            }
        }
    }
    None
}
