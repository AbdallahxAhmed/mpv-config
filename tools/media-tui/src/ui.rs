use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{
        Block, BorderType, Borders, Cell, Paragraph, Row, Table, Wrap,
    },
    Frame,
};
use ratatui_image::StatefulImage;
use ratatui_image::protocol::StatefulProtocol;
use crate::app::{App, ArtworkMode, ViewMode};
use crate::models::ProviderFilter;

// MovieBox Catppuccin Mocha Color Palette
const COLOR_MANTLE: Color = Color::Rgb(24, 24, 37);     // #181825
const COLOR_SURFACE0: Color = Color::Rgb(49, 50, 68);   // #313244
const COLOR_SURFACE1: Color = Color::Rgb(69, 71, 90);   // #45475A
const COLOR_SURFACE2: Color = Color::Rgb(88, 91, 112);  // #585B70
const COLOR_TEXT: Color = Color::Rgb(205, 214, 244);     // #CDD6F4
const COLOR_SUBTEXT0: Color = Color::Rgb(166, 173, 200); // #A6ADC8
const COLOR_BLUE: Color = Color::Rgb(137, 180, 250);    // #89B4FA
const COLOR_LAVENDER: Color = Color::Rgb(180, 190, 254);// #B4BEFE
const COLOR_MAUVE: Color = Color::Rgb(203, 166, 247);   // #CBA6F7
const COLOR_GREEN: Color = Color::Rgb(166, 227, 161);   // #A6E3A1
const COLOR_YELLOW: Color = Color::Rgb(249, 226, 175);  // #F9E2AF
const COLOR_PEACH: Color = Color::Rgb(250, 179, 135);   // #FAB387
const COLOR_TEAL: Color = Color::Rgb(148, 226, 213);    // #94E2D5
const COLOR_RED: Color = Color::Rgb(243, 139, 168);     // #F38BA8

pub fn render_ui(frame: &mut Frame, app: &mut App) {
    let size = frame.area();

    match app.view_mode() {
        ViewMode::Landing => render_landing_screen(frame, app, size),
        ViewMode::Results => render_results_screen(frame, app, size),
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. LANDING SCREEN (MovieBox-TUI Home Screen)
// ─────────────────────────────────────────────────────────────────────────────
fn render_landing_screen(frame: &mut Frame, app: &App, area: Rect) {
    // Center column layout
    let target_width = 72.min(area.width.saturating_sub(4)).max(30);
    let horiz_pad = (area.width.saturating_sub(target_width)) / 2;

    let col_area = Rect {
        x: area.x + horiz_pad,
        y: area.y,
        width: target_width,
        height: area.height,
    };

    let top_pad = if area.height >= 34 { 3 } else { 1 };
    let logo_height = 5;

    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(top_pad),        // Top padding
            Constraint::Length(logo_height),    // MOVIEBOX 3D ASCII Banner
            Constraint::Length(1),              // Subtitle v0.1.24
            Constraint::Length(1),              // Gap
            Constraint::Length(3),              // Centered Search Box
            Constraint::Length(1),              // Gap
            Constraint::Length(7),              // Discover Categories
            Constraint::Min(1),                 // Fill
            Constraint::Length(1),              // Footer
        ])
        .split(col_area);

    // 1. ASCII 3D Banner
    let logo_lines = vec![
        Line::from(Span::styled("███    ███  ██████  ██    ██ ██ ███████ ██████   ██████  ██   ██", Style::default().fg(COLOR_MAUVE).add_modifier(Modifier::BOLD))),
        Line::from(Span::styled("████  ████ ██    ██ ██    ██ ██ ██      ██   ██ ██    ██  ██ ██ ", Style::default().fg(COLOR_MAUVE).add_modifier(Modifier::BOLD))),
        Line::from(Span::styled("██ ████ ██ ██    ██ ██    ██ ██ █████   ██████  ██    ██   ███  ", Style::default().fg(COLOR_MAUVE).add_modifier(Modifier::BOLD))),
        Line::from(Span::styled("██  ██  ██ ██    ██  ██  ██  ██ ██      ██   ██ ██    ██  ██ ██ ", Style::default().fg(COLOR_MAUVE).add_modifier(Modifier::BOLD))),
        Line::from(Span::styled("██      ██  ██████    ████   ██ ███████ ██████   ██████  ██   ██", Style::default().fg(COLOR_MAUVE).add_modifier(Modifier::BOLD))),
    ];
    let logo_p = Paragraph::new(logo_lines).alignment(Alignment::Center);
    frame.render_widget(logo_p, rows[1]);

    // 2. Version
    let ver_p = Paragraph::new(Line::from(Span::styled("v0.1.24", Style::default().fg(COLOR_SUBTEXT0))))
        .alignment(Alignment::Center);
    frame.render_widget(ver_p, rows[2]);

    // 3. Search Box
    let search_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(COLOR_BLUE));

    let prompt = Span::styled("❯ ", Style::default().fg(COLOR_GREEN).add_modifier(Modifier::BOLD));
    let query_span = if app.query_input.is_empty() {
        Span::styled("Search movies, series & anime...", Style::default().fg(COLOR_SURFACE2))
    } else {
        Span::styled(&app.query_input, Style::default().fg(Color::White).add_modifier(Modifier::BOLD))
    };
    let cursor_span = Span::styled("▋", Style::default().fg(COLOR_BLUE));

    let active_provider_tag = match app.active_filter {
        ProviderFilter::All => "MovieBox • Tab",
        ProviderFilter::HentaiMama => "Mama • Tab",
        ProviderFilter::MuchoHentai => "Mucho • Tab",
        ProviderFilter::Nyaa => "Nyaa • Tab",
        ProviderFilter::Hanime => "Hanime • Tab",
        ProviderFilter::HentaiWorld => "World • Tab",
        ProviderFilter::HentaiHaven => "Haven • Tab",
    };
    let tag_span = Span::styled(format!("  [{}]", active_provider_tag), Style::default().fg(COLOR_BLUE));

    let search_line = Line::from(vec![
        Span::raw(" "),
        prompt,
        query_span,
        cursor_span,
        Span::raw("  "),
        tag_span,
    ]);
    let search_p = Paragraph::new(search_line).block(search_block);
    frame.render_widget(search_p, rows[4]);

    // 4. Discover Categories Card
    let disc_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(COLOR_SURFACE1))
        .title(Line::from(vec![
            Span::styled(" ✦ Discover Categories ", Style::default().fg(COLOR_TEXT).add_modifier(Modifier::BOLD)),
            Span::styled("──────────────────────── [ /browse ] ", Style::default().fg(COLOR_SURFACE1)),
        ]));

    let cat_lines = vec![
        Line::from(vec![
            Span::styled("  • Trending Now            ", Style::default().fg(COLOR_TEAL).add_modifier(Modifier::BOLD)),
            Span::styled("Popular & In-Theaters", Style::default().fg(COLOR_SUBTEXT0)),
        ]),
        Line::from(vec![
            Span::styled("  • Top Rated Series        ", Style::default().fg(COLOR_TEAL).add_modifier(Modifier::BOLD)),
            Span::styled("Critically Acclaimed TV", Style::default().fg(COLOR_SUBTEXT0)),
        ]),
        Line::from(vec![
            Span::styled("  • Latest Releases         ", Style::default().fg(COLOR_TEAL).add_modifier(Modifier::BOLD)),
            Span::styled("Recent 4K & HD Additions", Style::default().fg(COLOR_SUBTEXT0)),
        ]),
        Line::from(vec![
            Span::styled("  • Most Watched            ", Style::default().fg(COLOR_TEAL).add_modifier(Modifier::BOLD)),
            Span::styled("Community Favorites", Style::default().fg(COLOR_SUBTEXT0)),
        ]),
    ];
    let disc_p = Paragraph::new(cat_lines).block(disc_block);
    frame.render_widget(disc_p, rows[6]);

    // 5. Landing Footer
    let footer_line = Line::from(vec![
        Span::styled("[Tab]", Style::default().fg(COLOR_PEACH).add_modifier(Modifier::BOLD)),
        Span::styled(" Provider   ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("[Enter]", Style::default().fg(COLOR_GREEN).add_modifier(Modifier::BOLD)),
        Span::styled(" Search   ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("[?]", Style::default().fg(COLOR_YELLOW).add_modifier(Modifier::BOLD)),
        Span::styled(" Help   ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("[q]", Style::default().fg(COLOR_RED).add_modifier(Modifier::BOLD)),
        Span::styled(" Quit", Style::default().fg(COLOR_SUBTEXT0)),
    ]);
    let footer_p = Paragraph::new(footer_line).alignment(Alignment::Center);
    frame.render_widget(footer_p, rows[8]);
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. RESULTS SCREEN (MovieBox-TUI Search & Details Deck)
// ─────────────────────────────────────────────────────────────────────────────
fn render_results_screen(frame: &mut Frame, app: &mut App, area: Rect) {
    let showcase_height = if area.height >= 38 {
        16
    } else if area.height >= 30 {
        14
    } else {
        11
    };

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),               // Top Header
            Constraint::Length(1),               // Provider Pills
            Constraint::Length(showcase_height), // Master Media Showcase
            Constraint::Min(8),                  // Episodes & Streams Catalog
            Constraint::Length(1),               // Footer Shortcuts
        ])
        .split(area);

    render_results_header(frame, app, chunks[0]);
    render_provider_pills(frame, app, chunks[1]);
    render_details_showcase(frame, app, chunks[2]);
    render_catalog_table(frame, app, chunks[3]);
    render_footer(frame, app, chunks[4]);
}

fn render_results_header(frame: &mut Frame, app: &App, area: Rect) {
    let border_color = if app.is_editing_search {
        COLOR_BLUE
    } else {
        COLOR_SURFACE2
    };

    let prompt_span = if app.is_editing_search {
        Span::styled(" ❯ ", Style::default().fg(COLOR_GREEN).add_modifier(Modifier::BOLD))
    } else {
        Span::styled(" ❯ ", Style::default().fg(COLOR_SUBTEXT0))
    };

    let query_span = if app.query_input.is_empty() {
        Span::styled("Type a title to search...", Style::default().fg(COLOR_SURFACE2))
    } else {
        Span::styled(&app.query_input, Style::default().fg(Color::White).add_modifier(Modifier::BOLD))
    };

    let cursor_span = if app.is_editing_search {
        Span::styled("▋", Style::default().fg(COLOR_BLUE))
    } else {
        Span::raw("")
    };

    let result_text = if app.is_searching {
        "⏳ Querying 6 Providers...".to_string()
    } else {
        let count = app.all_results.len();
        if count == 1 {
            "1 result".to_string()
        } else {
            format!("{} results", count)
        }
    };

    let status_badge = Span::styled(
        result_text,
        Style::default().fg(if app.is_searching { COLOR_YELLOW } else { COLOR_SUBTEXT0 }).add_modifier(Modifier::BOLD),
    );

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    let left_para = Paragraph::new(Line::from(vec![prompt_span, query_span, cursor_span]));
    let right_para = Paragraph::new(Line::from(status_badge)).alignment(Alignment::Right);

    frame.render_widget(left_para, inner);
    frame.render_widget(right_para, inner);
}

fn render_provider_pills(frame: &mut Frame, app: &App, area: Rect) {
    let all_filters = ProviderFilter::all();
    let mut spans = vec![
        Span::styled(" Sources [Tab]: ", Style::default().fg(COLOR_SUBTEXT0).add_modifier(Modifier::BOLD))
    ];

    for f in all_filters {
        let count = if *f == ProviderFilter::All {
            app.all_results.len()
        } else {
            app.all_results
                .iter()
                .filter(|r| match f {
                    ProviderFilter::All => true,
                    ProviderFilter::HentaiMama => r.provider.eq_ignore_ascii_case("HentaiMama"),
                    ProviderFilter::MuchoHentai => r.provider.eq_ignore_ascii_case("MuchoHentai"),
                    ProviderFilter::Nyaa => r.provider.to_lowercase().contains("nyaa"),
                    ProviderFilter::Hanime => r.provider.eq_ignore_ascii_case("Hanime"),
                    ProviderFilter::HentaiWorld => r.provider.eq_ignore_ascii_case("HentaiWorld"),
                    ProviderFilter::HentaiHaven => r.provider.eq_ignore_ascii_case("HentaiHaven"),
                })
                .count()
        };

        let short_name = match f {
            ProviderFilter::All => "All",
            ProviderFilter::HentaiMama => "Mama",
            ProviderFilter::MuchoHentai => "Mucho",
            ProviderFilter::Nyaa => "Nyaa (P2P)",
            ProviderFilter::Hanime => "Hanime",
            ProviderFilter::HentaiWorld => "HWorld",
            ProviderFilter::HentaiHaven => "Haven",
        };

        let is_active = f == &app.active_filter;
        let pill_style = if is_active {
            Style::default()
                .fg(COLOR_MANTLE)
                .bg(COLOR_BLUE)
                .add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(COLOR_SUBTEXT0)
        };

        let label = format!(" {} ({}) ", short_name, count);
        spans.push(Span::styled(label, pill_style));
        spans.push(Span::raw(" "));
    }

    let para = Paragraph::new(Line::from(spans));
    frame.render_widget(para, area);
}

fn render_details_showcase(frame: &mut Frame, app: &mut App, area: Rect) {
    let Some(selected) = app.selected_result().cloned() else {
        let block = Block::default()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::default().fg(COLOR_SURFACE2))
            .title(Span::styled(" ℹ Media Details & Artwork ", Style::default().fg(COLOR_SUBTEXT0)));
        let msg = Paragraph::new("\n  Select a stream from the catalog below to inspect episode artwork, technical specifications, and synopsis.")
            .style(Style::default().fg(COLOR_SUBTEXT0))
            .block(block);
        frame.render_widget(msg, area);
        return;
    };

    // Split showcase horizontally:
    // Left: Artwork Card (~28 width)
    // Right: MovieBox Metadata & Synopsis (remaining)
    let showcase_split = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Length(28), // 2:3 Artwork Card
            Constraint::Min(30),    // Details & Synopsis
        ])
        .split(area);

    // 1. Artwork Card (Hardware Sixel / Protocol)
    let (art_title, title_color) = match app.artwork_mode {
        ArtworkMode::EpisodeFrame => {
            if let Some(ref ep) = selected.episode {
                (format!(" 🖼 Video Frame (Ep {}) [p] ", ep), COLOR_PEACH)
            } else {
                (" 🖼 Video Frame [p] ".to_string(), COLOR_PEACH)
            }
        }
        ArtworkMode::SeriesPoster => {
            (" 🖼 Series Poster [p] ".to_string(), COLOR_MAUVE)
        }
    };

    let art_border = if app.artwork_mode == ArtworkMode::EpisodeFrame {
        COLOR_PEACH
    } else {
        COLOR_LAVENDER
    };

    let art_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(art_border))
        .title(Span::styled(art_title, Style::default().fg(title_color).add_modifier(Modifier::BOLD)));

    let inner_art_area = art_block.inner(showcase_split[0]);
    frame.render_widget(art_block, showcase_split[0]);

    if let Some(ref mut protocol) = app.image_protocol {
        let image_widget = StatefulImage::<StatefulProtocol>::default();
        frame.render_stateful_widget(image_widget, inner_art_area, protocol);
    } else {
        let mode_desc = match app.artwork_mode {
            ArtworkMode::EpisodeFrame => "Episode Frame",
            ArtworkMode::SeriesPoster => "Series Poster",
        };
        let placeholder = Paragraph::new(format!("\n\n   ⏳ Loading\n   {}...", mode_desc))
            .style(Style::default().fg(COLOR_SUBTEXT0));
        frame.render_widget(placeholder, inner_art_area);
    }

    // 2. Metadata & Plot Showcase (MovieBox Style)
    let meta_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(COLOR_SURFACE2))
        .title(Span::styled(" ℹ Media Details & Synopsis ─ Toggle Poster/Frame: [p] ", Style::default().fg(COLOR_MAUVE).add_modifier(Modifier::BOLD)));

    let official_title = selected
        .official_title
        .as_deref()
        .unwrap_or(selected.title.as_str());

    let studio_str = selected.studio.as_deref().unwrap_or("Studio Unknown");
    let year_str = selected.year.map(|y| y.to_string()).unwrap_or_else(|| "N/A".to_string());
    let rating_str = selected
        .rating
        .map(|r| format!("★ {:.1}", r / 10.0))
        .unwrap_or_else(|| "★ N/A".to_string());

    let censo_style = match selected.censorship.to_lowercase().as_str() {
        "uncensored" => Style::default().fg(COLOR_GREEN).add_modifier(Modifier::BOLD),
        "decensored" => Style::default().fg(COLOR_BLUE).add_modifier(Modifier::BOLD),
        _ => Style::default().fg(COLOR_YELLOW).add_modifier(Modifier::BOLD),
    };

    let target_ep = if let Some(ref ep) = selected.episode {
        format!("Episode {}", ep)
    } else {
        "Full Release".to_string()
    };

    let synopsis_text = selected
        .synopsis
        .as_deref()
        .unwrap_or("No plot overview available for this title.");

    let mut meta_lines = vec![
        // Row 1: Title (MovieBox highlighted style)
        Line::from(vec![
            Span::styled(format!(" {} ", official_title), Style::default().fg(Color::White).bg(COLOR_SURFACE1).add_modifier(Modifier::BOLD)),
        ]),
        // Row 2: Badges
        Line::from(vec![
            Span::styled(format!(" {} ", rating_str), Style::default().fg(COLOR_MANTLE).bg(COLOR_YELLOW).add_modifier(Modifier::BOLD)),
            Span::raw(" "),
            Span::styled(format!(" {} ", year_str), Style::default().fg(COLOR_TEXT).bg(COLOR_SURFACE0)),
            Span::raw(" "),
            Span::styled(format!(" {} ", studio_str), Style::default().fg(COLOR_PEACH).bg(COLOR_SURFACE0).add_modifier(Modifier::BOLD)),
            Span::raw(" "),
            Span::styled(format!(" [ {} ] ", selected.censorship.to_uppercase()), censo_style),
            Span::raw(" "),
            Span::styled(
                format!("{} Episodes", selected.episodes_count.map(|e| e.to_string()).unwrap_or_else(|| "OVA".to_string())),
                Style::default().fg(COLOR_SUBTEXT0),
            ),
        ]),
    ];

    // Row 3: Genres
    if !selected.genres.is_empty() {
        let mut genre_spans = vec![Span::styled("Genres: ", Style::default().fg(COLOR_SUBTEXT0))];
        for g in selected.genres.iter().take(5) {
            genre_spans.push(Span::styled(format!("[{}] ", g), Style::default().fg(COLOR_TEAL)));
        }
        meta_lines.push(Line::from(genre_spans));
    }

    // Row 4: Divider
    meta_lines.push(Line::from(Span::styled("────────────────────────────────────────────────────────────────────────────", Style::default().fg(COLOR_SURFACE1))));

    // Row 5: Active Stream Specs
    meta_lines.push(Line::from(vec![
        Span::styled("Selected: ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled(target_ep, Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
        Span::raw(" • "),
        Span::styled(&selected.provider, Style::default().fg(COLOR_BLUE).add_modifier(Modifier::BOLD)),
        Span::raw(" • "),
        Span::styled(&selected.resolution, Style::default().fg(COLOR_YELLOW).add_modifier(Modifier::BOLD)),
        Span::raw(" • "),
        Span::styled(&selected.codec, Style::default().fg(COLOR_TEXT)),
        Span::raw(" • "),
        Span::styled(&selected.delivery, Style::default().fg(COLOR_GREEN).add_modifier(Modifier::BOLD)),
        Span::raw(" • Audio: "),
        Span::styled(&selected.audio, Style::default().fg(COLOR_PEACH)),
    ]));

    // Row 6+: Plot Overview
    meta_lines.push(Line::from(vec![
        Span::styled("Plot: ", Style::default().fg(COLOR_YELLOW).add_modifier(Modifier::BOLD)),
        Span::styled(synopsis_text, Style::default().fg(COLOR_TEXT)),
    ]));

    let meta_para = Paragraph::new(meta_lines)
        .block(meta_block)
        .wrap(Wrap { trim: true });
    frame.render_widget(meta_para, showcase_split[1]);
}

fn render_catalog_table(frame: &mut Frame, app: &mut App, area: Rect) {
    let header_cells = [
        " #", "Source", "Episode & Title", "Res", "Format / Quality", "Delivery", "Score"
    ]
    .iter()
    .map(|h| {
        Cell::from(Span::styled(
            *h,
            Style::default()
                .fg(COLOR_MAUVE)
                .add_modifier(Modifier::BOLD),
        ))
    });
    let header = Row::new(header_cells).height(1).bottom_margin(1);

    let rows: Vec<Row> = app
        .filtered_indices
        .iter()
        .enumerate()
        .map(|(disp_idx, raw_idx)| {
            let r = &app.all_results[*raw_idx];

            let num_cell = Cell::from(Span::styled(
                format!("{:>2}.", disp_idx + 1),
                Style::default().fg(COLOR_SUBTEXT0),
            ));

            let (source_tag, source_color) = match r.provider.as_str() {
                "HentaiMama" => (" [MAMA] ", COLOR_PEACH),
                "MuchoHentai" => (" [MUCHO]", COLOR_TEAL),
                "Hanime" => (" [HANIME]", COLOR_RED),
                "Nyaa" => (" [NYAA] ", COLOR_GREEN),
                "HentaiWorld" => (" [WORLD] ", COLOR_MAUVE),
                _ => (" [OTHER] ", COLOR_TEXT),
            };
            let source_cell = Cell::from(Span::styled(
                source_tag,
                Style::default().fg(source_color).add_modifier(Modifier::BOLD),
            ));

            let title_display = if let Some(ref ep) = r.episode {
                format!("Ep {:>02} • {}", ep, r.title)
            } else {
                r.title.clone()
            };
            let title_cell = Cell::from(Span::styled(
                title_display,
                Style::default().fg(Color::White),
            ));

            let res_cell = Cell::from(Span::styled(
                &r.resolution,
                Style::default().fg(COLOR_BLUE).add_modifier(Modifier::BOLD),
            ));

            let quality_cell = Cell::from(Span::styled(
                format!("{} ({})", r.quality_type, r.codec),
                Style::default().fg(COLOR_TEXT),
            ));

            let (del_tag, del_color) = if r.delivery == "Instant CDN" {
                ("⚡ Instant CDN", COLOR_GREEN)
            } else {
                ("🧲 Torrent P2P", COLOR_YELLOW)
            };
            let del_cell = Cell::from(Span::styled(
                del_tag,
                Style::default().fg(del_color).add_modifier(Modifier::BOLD),
            ));

            let score_style = if r.score >= 85.0 {
                Style::default().fg(COLOR_GREEN).add_modifier(Modifier::BOLD)
            } else if r.score >= 70.0 {
                Style::default().fg(COLOR_YELLOW)
            } else {
                Style::default().fg(COLOR_PEACH)
            };
            let score_cell = Cell::from(Span::styled(format!("★ {:>2.0}", r.score), score_style));

            let row = Row::new(vec![num_cell, source_cell, title_cell, res_cell, quality_cell, del_cell, score_cell]);
            if disp_idx == app.selected_filtered_idx {
                row.style(
                    Style::default()
                        .bg(COLOR_SURFACE0)
                        .fg(Color::White)
                        .add_modifier(Modifier::BOLD),
                )
            } else {
                row
            }
        })
        .collect();

    let widths = [
        Constraint::Length(4),  // #
        Constraint::Length(10), // Source tag
        Constraint::Min(28),    // Title & Episode
        Constraint::Length(7),  // Res
        Constraint::Length(22), // Format & Codec
        Constraint::Length(16), // Delivery
        Constraint::Length(8),  // Score
    ];

    let count_text = format!(" 📋 Episodes & Streams Catalog ({}) ", app.filtered_indices.len());
    let table = Table::new(rows, widths)
        .header(header)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(Style::default().fg(COLOR_SURFACE2))
                .title(Span::styled(count_text, Style::default().fg(COLOR_BLUE).add_modifier(Modifier::BOLD))),
        )
        .highlight_symbol("▶ ");

    frame.render_stateful_widget(table, area, &mut app.table_state);
}

fn render_footer(frame: &mut Frame, app: &App, area: Rect) {
    let status_span = Span::styled(&app.status_message, Style::default().fg(COLOR_TEXT));

    let shortcuts_spans = vec![
        Span::styled("<Enter>", Style::default().fg(COLOR_GREEN).add_modifier(Modifier::BOLD)),
        Span::styled(" Stream ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("<Space>", Style::default().fg(COLOR_BLUE).add_modifier(Modifier::BOLD)),
        Span::styled(" Preview ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("<d>", Style::default().fg(COLOR_PEACH).add_modifier(Modifier::BOLD)),
        Span::styled(" Download ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("<p>", Style::default().fg(COLOR_MAUVE).add_modifier(Modifier::BOLD)),
        Span::styled(" Poster/Frame ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("<c>", Style::default().fg(COLOR_LAVENDER).add_modifier(Modifier::BOLD)),
        Span::styled(" Copy ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("</>", Style::default().fg(COLOR_YELLOW).add_modifier(Modifier::BOLD)),
        Span::styled(" Search ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("<Tab>", Style::default().fg(COLOR_TEAL).add_modifier(Modifier::BOLD)),
        Span::styled(" Filter ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("<Esc>", Style::default().fg(COLOR_TEXT).add_modifier(Modifier::BOLD)),
        Span::styled(" Home ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("<q>", Style::default().fg(COLOR_RED).add_modifier(Modifier::BOLD)),
        Span::styled(" Quit", Style::default().fg(COLOR_SUBTEXT0)),
    ];

    let footer_layout = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(34),
            Constraint::Percentage(66),
        ])
        .split(area);

    let status_para = Paragraph::new(Line::from(vec![Span::raw(" "), status_span]));
    let shortcuts_para = Paragraph::new(Line::from(shortcuts_spans));

    frame.render_widget(status_para, footer_layout[0]);
    frame.render_widget(shortcuts_para, footer_layout[1]);
}
