use std::path::PathBuf;
use tokio::process::Command;
use crate::models::{BridgeResponse, SearchResult};
use anyhow::{Result, Context};

fn find_script(relative_path: &str) -> PathBuf {
    let p = PathBuf::from(relative_path);
    if p.exists() {
        return p;
    }
    let p_up = PathBuf::from("..").join(relative_path);
    if p_up.exists() {
        return p_up;
    }
    let p_up2 = PathBuf::from("../..").join(relative_path);
    if p_up2.exists() {
        return p_up2;
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let candidate1 = dir.join("../../").join(relative_path);
            if candidate1.exists() {
                return candidate1;
            }
            let candidate2 = dir.join("../../../").join(relative_path);
            if candidate2.exists() {
                return candidate2;
            }
        }
    }
    PathBuf::from(relative_path)
}

pub async fn run_search_bridge(query: &str) -> Result<Vec<SearchResult>> {
    let script = find_script("tools/search/json_bridge.py");
    let output = Command::new("python")
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
    let script = find_script("tools/search/fetch_image.py");
    let output = Command::new("python")
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
