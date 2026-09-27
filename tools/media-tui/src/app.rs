use std::path::PathBuf;
use std::process::Child;
use ratatui::widgets::TableState;
use ratatui_image::picker::Picker;
use ratatui_image::protocol::StatefulProtocol;
use tokio::sync::mpsc;
use crate::models::{ProviderFilter, SearchResult};
use crate::bridge::{run_search_bridge, download_image_to_cache};
use crate::mpv;

#[derive(Debug)]
pub enum AppAction {
    SearchCompleted(anyhow::Result<Vec<SearchResult>>),
    ImageLoaded { url: String, path: PathBuf },
    SetStatus(String),
}

pub struct App {
    pub query_input: String,
    pub is_editing_search: bool,
    pub active_filter: ProviderFilter,
    pub all_results: Vec<SearchResult>,
    pub filtered_indices: Vec<usize>,
    pub selected_filtered_idx: usize,
    pub table_state: TableState,
    pub is_searching: bool,
    pub status_message: String,
    pub picker: Picker,
    pub image_protocol: Option<StatefulProtocol>,
    pub current_image_url: Option<String>,
    pub mpv_child: Option<Child>,
    pub should_quit: bool,
}

impl App {
    pub fn new() -> Self {
        let picker = Picker::from_query_stdio().unwrap_or_else(|_| {
            Picker::halfblocks()
        });

        let mut app = Self {
            query_input: String::new(),
            is_editing_search: true,
            active_filter: ProviderFilter::All,
            all_results: Vec::new(),
            filtered_indices: Vec::new(),
            selected_filtered_idx: 0,
            table_state: TableState::default(),
            is_searching: false,
            status_message: "Type a query and press <Enter> to search across all 6 providers".to_string(),
            picker,
            image_protocol: None,
            current_image_url: None,
            mpv_child: None,
            should_quit: false,
        };
        app.table_state.select(Some(0));
        app
    }

    pub fn selected_result(&self) -> Option<&SearchResult> {
        if self.filtered_indices.is_empty() {
            return None;
        }
        let raw_idx = self.filtered_indices.get(self.selected_filtered_idx)?;
        self.all_results.get(*raw_idx)
    }

    pub fn apply_filter(&mut self) {
        self.filtered_indices.clear();
        for (i, r) in self.all_results.iter().enumerate() {
            let matches = match self.active_filter {
                ProviderFilter::All => true,
                ProviderFilter::HentaiMama => r.provider.eq_ignore_ascii_case("HentaiMama"),
                ProviderFilter::MuchoHentai => r.provider.eq_ignore_ascii_case("MuchoHentai"),
                ProviderFilter::Nyaa => r.provider.to_lowercase().contains("nyaa"),
                ProviderFilter::Hanime => r.provider.eq_ignore_ascii_case("Hanime"),
                ProviderFilter::HentaiWorld => r.provider.eq_ignore_ascii_case("HentaiWorld"),
                ProviderFilter::HentaiHaven => r.provider.eq_ignore_ascii_case("HentaiHaven"),
            };
            if matches {
                self.filtered_indices.push(i);
            }
        }

        if self.filtered_indices.is_empty() {
            self.selected_filtered_idx = 0;
            self.table_state.select(None);
        } else {
            if self.selected_filtered_idx >= self.filtered_indices.len() {
                self.selected_filtered_idx = 0;
            }
            self.table_state.select(Some(self.selected_filtered_idx));
        }
    }

    pub fn next_filter(&mut self) {
        let all = ProviderFilter::all();
        let curr_pos = all.iter().position(|f| f == &self.active_filter).unwrap_or(0);
        let next_pos = (curr_pos + 1) % all.len();
        self.active_filter = all[next_pos].clone();
        self.apply_filter();
    }

    pub fn prev_filter(&mut self) {
        let all = ProviderFilter::all();
        let curr_pos = all.iter().position(|f| f == &self.active_filter).unwrap_or(0);
        let prev_pos = if curr_pos == 0 { all.len() - 1 } else { curr_pos - 1 };
        self.active_filter = all[prev_pos].clone();
        self.apply_filter();
    }

    pub fn select_next(&mut self) {
        if self.filtered_indices.is_empty() {
            return;
        }
        if self.selected_filtered_idx + 1 < self.filtered_indices.len() {
            self.selected_filtered_idx += 1;
        } else {
            self.selected_filtered_idx = 0;
        }
        self.table_state.select(Some(self.selected_filtered_idx));
    }

    pub fn select_prev(&mut self) {
        if self.filtered_indices.is_empty() {
            return;
        }
        if self.selected_filtered_idx > 0 {
            self.selected_filtered_idx -= 1;
        } else {
            self.selected_filtered_idx = self.filtered_indices.len() - 1;
        }
        self.table_state.select(Some(self.selected_filtered_idx));
    }

    pub fn start_search(&mut self, action_tx: mpsc::Sender<AppAction>) {
        let q = self.query_input.trim().to_string();
        if q.is_empty() {
            return;
        }

        self.is_searching = true;
        self.status_message = format!("Searching all 6 providers for '{}'...", q);
        self.is_editing_search = false;

        tokio::spawn(async move {
            let res = run_search_bridge(&q).await;
            let _ = action_tx.send(AppAction::SearchCompleted(res)).await;
        });
    }

    pub fn trigger_image_load_for_selected(&mut self, action_tx: mpsc::Sender<AppAction>) {
        let target_url = if let Some(r) = self.selected_result() {
            r.poster_url.as_ref().or(r.thumbnail.as_ref()).cloned()
        } else {
            None
        };

        let Some(url) = target_url else {
            self.image_protocol = None;
            self.current_image_url = None;
            return;
        };

        if self.current_image_url.as_deref() == Some(&url) {
            return; // already loaded or loading
        }

        self.current_image_url = Some(url.clone());
        let tx = action_tx.clone();
        let url_clone = url.clone();

        tokio::spawn(async move {
            if let Some(path) = download_image_to_cache(&url_clone).await {
                let _ = tx.send(AppAction::ImageLoaded { url: url_clone, path }).await;
            }
        });
    }

    pub fn update_image_from_file(&mut self, path: PathBuf) {
        if let Ok(dyn_img) = image::open(&path) {
            let protocol = self.picker.new_resize_protocol(dyn_img);
            self.image_protocol = Some(protocol);
        }
    }

    pub fn handle_action(&mut self, action: AppAction, action_tx: mpsc::Sender<AppAction>) {
        match action {
            AppAction::SearchCompleted(Ok(results)) => {
                self.is_searching = false;
                let count = results.len();
                self.all_results = results;
                self.apply_filter();
                self.status_message = format!("Found and ranked {} sources across providers", count);
                self.trigger_image_load_for_selected(action_tx);
            }
            AppAction::SearchCompleted(Err(e)) => {
                self.is_searching = false;
                self.status_message = format!("Search failed: {}", e);
            }
            AppAction::ImageLoaded { url, path } => {
                if self.current_image_url.as_deref() == Some(&url) {
                    self.update_image_from_file(path);
                }
            }
            AppAction::SetStatus(msg) => {
                self.status_message = msg;
            }
        }
    }

    pub fn play_selected(&mut self) {
        if let Some(r) = self.selected_result().cloned() {
            self.status_message = format!("🎬 Playing in MPV: {}", r.title);
            let _ = mpv::play_in_mpv(&r);
        }
    }

    pub fn preview_selected(&mut self) {
        if let Some(r) = self.selected_result().cloned() {
            self.status_message = format!("👁 Floating Preview: {}", r.title);
            if let Ok(child) = mpv::preview_floating(&r) {
                self.mpv_child = Some(child);
            }
        }
    }

    pub fn download_selected(&mut self) {
        if let Some(r) = self.selected_result().cloned() {
            self.status_message = format!("⚡ Turbo Download: {}", r.title);
            let _ = mpv::download_item(&r);
        }
    }

    pub fn copy_selected_url(&mut self) {
        if let Some(r) = self.selected_result().cloned() {
            let url = r.download_url.as_ref().unwrap_or(&r.url);
            mpv::copy_to_clipboard(url);
            self.status_message = format!("✔ Copied URL to clipboard: {}", url);
        }
    }
}
