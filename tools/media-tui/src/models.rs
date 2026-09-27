use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub title: String,
    pub provider: String,
    pub url: String,
    #[serde(default)]
    pub download_url: Option<String>,
    #[serde(default = "default_res")]
    pub resolution: String,
    #[serde(default = "default_quality")]
    pub quality_type: String,
    #[serde(default = "default_codec")]
    pub codec: String,
    #[serde(default)]
    pub size: String,
    #[serde(default)]
    pub seeders: Option<i64>,
    #[serde(default = "default_censorship")]
    pub censorship: String,
    #[serde(default = "default_subtitles")]
    pub subtitles: String,
    #[serde(default = "default_audio")]
    pub audio: String,
    #[serde(default = "default_delivery")]
    pub delivery: String,
    #[serde(default)]
    pub thumbnail: Option<String>,
    #[serde(default)]
    pub score: f64,
    #[serde(default)]
    pub badges: Vec<String>,
    #[serde(default)]
    pub is_best: bool,
    #[serde(default)]
    pub episode: Option<String>,
    #[serde(default)]
    pub poster_url: Option<String>,
    #[serde(default)]
    pub official_title: Option<String>,
    #[serde(default)]
    pub rating: Option<f64>,
    #[serde(default)]
    pub genres: Vec<String>,
    #[serde(default)]
    pub year: Option<i64>,
    #[serde(default)]
    pub synopsis: Option<String>,
    #[serde(default)]
    pub studio: Option<String>,
    #[serde(default)]
    pub episodes_count: Option<i64>,
}

fn default_res() -> String {
    "1080p".to_string()
}
fn default_quality() -> String {
    "Web Stream".to_string()
}
fn default_codec() -> String {
    "H.264".to_string()
}
fn default_censorship() -> String {
    "Censored".to_string()
}
fn default_subtitles() -> String {
    "Hard-sub".to_string()
}
fn default_audio() -> String {
    "Japanese (Original)".to_string()
}
fn default_delivery() -> String {
    "Instant CDN".to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BridgeResponse {
    pub status: String,
    #[serde(default)]
    pub query: String,
    #[serde(default)]
    pub count: usize,
    #[serde(default)]
    pub results: Vec<SearchResult>,
    #[serde(default)]
    pub error: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProviderFilter {
    All,
    HentaiMama,
    MuchoHentai,
    Nyaa,
    Hanime,
    HentaiWorld,
    HentaiHaven,
}

impl ProviderFilter {
    #[allow(dead_code)]
    pub fn name(&self) -> &'static str {
        match self {
            Self::All => "All Sources",
            Self::HentaiMama => "HentaiMama",
            Self::MuchoHentai => "MuchoHentai",
            Self::Nyaa => "Nyaa (P2P)",
            Self::Hanime => "Hanime",
            Self::HentaiWorld => "HentaiWorld",
            Self::HentaiHaven => "HentaiHaven",
        }
    }

    pub fn all() -> &'static [ProviderFilter] {
        &[
            Self::All,
            Self::HentaiMama,
            Self::MuchoHentai,
            Self::Nyaa,
            Self::Hanime,
            Self::HentaiWorld,
            Self::HentaiHaven,
        ]
    }
}
