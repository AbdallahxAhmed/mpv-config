use std::path::PathBuf;
use tokio::process::Command;
use crate::models::{BridgeResponse, SearchResult};
use anyhow::{Result, Context};

pub async fn run_search_bridge(query: &str) -> Result<Vec<SearchResult>> {
    let output = Command::new("python")
        .arg("tools/search/json_bridge.py")
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
    let output = Command::new("python")
        .arg("tools/search/fetch_image.py")
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
