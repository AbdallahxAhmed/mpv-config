use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{
        Block, BorderType, Borders, Cell, Paragraph, Row, Table, Wrap,
    },
    Frame,
};
use ratatui_image::StatefulImage;
use ratatui_image::protocol::StatefulProtocol;
use crate::app::App;
use crate::models::ProviderFilter;

// MovieBox Catppuccin Mocha Color Palette
const COLOR_MANTLE: Color = Color::Rgb(24, 24, 37);     // #181825
const COLOR_SURFACE0: Color = Color::Rgb(49, 50, 68);   // #313244
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

    // MovieBox Vertical Layout:
    // 1. Unified Search & Brand Header (3 rows)
    // 2. Clean Provider Filter Pills (1 row)
    // 3. Main Dual-Pane Catalog & Showcase (Min 10 rows)
    // 4. Clean Footer Keybindings (1 row)
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // Top Header
            Constraint::Length(1), // Provider Pills
            Constraint::Min(10),   // Dual-Pane Catalog & Showcase
            Constraint::Length(1), // Footer Shortcuts
        ])
        .split(size);

    render_header(frame, app, chunks[0]);
    render_provider_pills(frame, app, chunks[1]);
    render_main_showcase(frame, app, chunks[2]);
    render_footer(frame, app, chunks[3]);
}

fn render_header(frame: &mut Frame, app: &App, area: Rect) {
    let border_color = if app.is_editing_search {
        COLOR_BLUE
    } else {
        COLOR_SURFACE2
    };

    let brand_span = Span::styled(
        " 🎞 MOVIEBOX-TUI ",
        Style::default().fg(COLOR_MAUVE).add_modifier(Modifier::BOLD),
    );

    let prompt_span = if app.is_editing_search {
        Span::styled(" ❯ Search: ", Style::default().fg(COLOR_GREEN).add_modifier(Modifier::BOLD))
    } else {
        Span::styled(" ❯ Search: ", Style::default().fg(COLOR_SUBTEXT0))
    };

    let query_span = if app.query_input.is_empty() {
        if app.is_editing_search {
            Span::styled("Type a title to search (e.g. imaria, overflow)...", Style::default().fg(COLOR_SURFACE2))
        } else {
            Span::styled("Press '/' or Enter to search", Style::default().fg(COLOR_SURFACE2))
        }
    } else {
        Span::styled(&app.query_input, Style::default().fg(Color::White).add_modifier(Modifier::BOLD))
    };

    let cursor_span = if app.is_editing_search {
        Span::styled("▋", Style::default().fg(COLOR_BLUE))
    } else {
        Span::raw("")
    };

    let status_badge = if app.is_searching {
        Span::styled(
            " [ ⏳ Querying 6 Providers... ] ",
            Style::default().fg(COLOR_YELLOW).add_modifier(Modifier::BOLD),
        )
    } else if !app.all_results.is_empty() {
        Span::styled(
            format!(" [ {} Sources Ready ] ", app.all_results.len()),
            Style::default().fg(COLOR_GREEN).add_modifier(Modifier::BOLD),
        )
    } else {
        Span::raw("")
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color));

    let header_line = Line::from(vec![
        brand_span,
        Span::styled("│", Style::default().fg(COLOR_SURFACE2)),
        prompt_span,
        query_span,
        cursor_span,
        Span::raw("  "),
        status_badge,
    ]);

    let paragraph = Paragraph::new(header_line).block(block);
    frame.render_widget(paragraph, area);
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

fn render_main_showcase(frame: &mut Frame, app: &mut App, area: Rect) {
    let dual_pane = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(47), // Left: Catalog Table
            Constraint::Percentage(53), // Right: MovieBox Details Showcase
        ])
        .split(area);

    render_catalog_table(frame, app, dual_pane[0]);
    render_details_showcase(frame, app, dual_pane[1]);
}

fn render_catalog_table(frame: &mut Frame, app: &mut App, area: Rect) {
    let header_cells = [
        " #", "Source", "Episode / Title", "Res", "Type", "Score"
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

            // Format episode / title cleanly
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

            let (del_tag, del_color) = if r.delivery == "Instant CDN" {
                ("CDN", COLOR_GREEN)
            } else {
                ("P2P", COLOR_YELLOW)
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
            let score_cell = Cell::from(Span::styled(format!("★{:>2.0}", r.score), score_style));

            let row = Row::new(vec![num_cell, source_cell, title_cell, res_cell, del_cell, score_cell]);
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
        Constraint::Length(9),  // Source tag
        Constraint::Min(20),    // Title & Episode
        Constraint::Length(6),  // Res
        Constraint::Length(5),  // Delivery
        Constraint::Length(6),  // Score
    ];

    let count_text = format!(" 📋 Media Catalog ({}) ", app.filtered_indices.len());
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

fn render_details_showcase(frame: &mut Frame, app: &mut App, area: Rect) {
    let Some(selected) = app.selected_result().cloned() else {
        let block = Block::default()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::default().fg(COLOR_SURFACE2))
            .title(Span::styled(" ℹ Media Showcase ", Style::default().fg(COLOR_SUBTEXT0)));
        let msg = Paragraph::new("\n  Select a stream from the catalog table to inspect episode artwork and stream specifications.")
            .style(Style::default().fg(COLOR_SUBTEXT0))
            .block(block);
        frame.render_widget(msg, area);
        return;
    };

    // Split showcase vertically:
    // Top 60%: Artwork & Metadata
    // Bottom 40%: Overview & Stream URL
    let showcase_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(19), // Poster + Meta
            Constraint::Min(6),     // Plot Overview + Stream Link
        ])
        .split(area);

    // Split Top Section into: Left (Artwork ~45%), Right (Metadata ~55%)
    let top_split = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(45), // Artwork Card
            Constraint::Percentage(55), // Metadata Card
        ])
        .split(showcase_chunks[0]);

    // 1. Artwork Card (Hardware Sixel)
    let art_title = if let Some(ref ep) = selected.episode {
        format!(" 🖼 Episode {} Preview ", ep)
    } else {
        " 🖼 Artwork Preview ".to_string()
    };

    let art_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(COLOR_LAVENDER))
        .title(Span::styled(art_title, Style::default().fg(COLOR_LAVENDER).add_modifier(Modifier::BOLD)));

    let inner_art_area = art_block.inner(top_split[0]);
    frame.render_widget(art_block, top_split[0]);

    if let Some(ref mut protocol) = app.image_protocol {
        let image_widget = StatefulImage::<StatefulProtocol>::default();
        frame.render_stateful_widget(image_widget, inner_art_area, protocol);
    } else {
        let placeholder = Paragraph::new("\n\n   ⏳ Loading\n   Episode\n   Artwork...")
            .style(Style::default().fg(COLOR_SUBTEXT0));
        frame.render_widget(placeholder, inner_art_area);
    }

    // 2. Metadata Card (MovieBox-Style)
    let meta_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(COLOR_SURFACE2))
        .title(Span::styled(" ℹ Media Details ", Style::default().fg(COLOR_MAUVE).add_modifier(Modifier::BOLD)));

    let official_title = selected
        .official_title
        .as_deref()
        .unwrap_or(selected.title.as_str());

    let studio_str = selected.studio.as_deref().unwrap_or("Studio Unknown");
    let year_str = selected.year.map(|y| y.to_string()).unwrap_or_else(|| "N/A".to_string());
    let rating_str = selected
        .rating
        .map(|r| format!("★ {:.1}", r / 10.0))
        .unwrap_or_else(|| "N/A".to_string());

    let censo_style = match selected.censorship.to_lowercase().as_str() {
        "uncensored" => Style::default().fg(COLOR_GREEN).add_modifier(Modifier::BOLD),
        "decensored" => Style::default().fg(COLOR_BLUE).add_modifier(Modifier::BOLD),
        _ => Style::default().fg(COLOR_YELLOW).add_modifier(Modifier::BOLD),
    };

    let mut meta_lines = vec![
        // Title
        Line::from(Span::styled(
            official_title,
            Style::default().fg(COLOR_MAUVE).add_modifier(Modifier::BOLD),
        )),
        // Rating & Studio Pills
        Line::from(vec![
            Span::styled(format!(" {} ", rating_str), Style::default().fg(COLOR_MANTLE).bg(COLOR_YELLOW).add_modifier(Modifier::BOLD)),
            Span::raw(" "),
            Span::styled(format!(" {} ", year_str), Style::default().fg(COLOR_TEXT).bg(COLOR_SURFACE0)),
            Span::raw(" "),
            Span::styled(format!(" {} ", studio_str), Style::default().fg(COLOR_PEACH).bg(COLOR_SURFACE0)),
        ]),
        // Status & Episodes
        Line::from(vec![
            Span::styled("Status: ", Style::default().fg(COLOR_SUBTEXT0)),
            Span::styled(format!("[ {} ]", selected.censorship.to_uppercase()), censo_style),
            Span::raw("  "),
            Span::styled(
                format!("Eps: {}", selected.episodes_count.map(|e| e.to_string()).unwrap_or_else(|| "OVA".to_string())),
                Style::default().fg(COLOR_SUBTEXT0),
            ),
        ]),
    ];

    // Genres
    if !selected.genres.is_empty() {
        let mut genre_spans = vec![Span::styled("Genres: ", Style::default().fg(COLOR_SUBTEXT0))];
        for g in selected.genres.iter().take(3) {
            genre_spans.push(Span::styled(format!("[{}] ", g), Style::default().fg(COLOR_TEAL)));
        }
        meta_lines.push(Line::from(genre_spans));
    }

    meta_lines.push(Line::from(Span::styled("──────────────────────────────", Style::default().fg(COLOR_SURFACE2))));

    // Target Selection Info
    let target_ep = if let Some(ref ep) = selected.episode {
        format!("Episode {}", ep)
    } else {
        "Full Release".to_string()
    };

    meta_lines.push(Line::from(vec![
        Span::styled("Selected:  ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled(target_ep, Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
    ]));

    meta_lines.push(Line::from(vec![
        Span::styled("Source:    ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled(&selected.provider, Style::default().fg(COLOR_BLUE).add_modifier(Modifier::BOLD)),
        Span::raw(" • "),
        Span::styled(&selected.delivery, Style::default().fg(COLOR_GREEN)),
    ]));

    meta_lines.push(Line::from(vec![
        Span::styled("Format:    ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled(&selected.resolution, Style::default().fg(COLOR_BLUE)),
        Span::raw(" • "),
        Span::styled(&selected.codec, Style::default().fg(COLOR_TEXT)),
    ]));

    meta_lines.push(Line::from(vec![
        Span::styled("Audio:     ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled(&selected.audio, Style::default().fg(COLOR_PEACH)),
    ]));

    meta_lines.push(Line::from(vec![
        Span::styled("Subs:      ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled(&selected.subtitles, Style::default().fg(COLOR_TEXT)),
    ]));

    if let Some(seeders) = selected.seeders {
        meta_lines.push(Line::from(vec![
            Span::styled("Seeds:     ", Style::default().fg(COLOR_SUBTEXT0)),
            Span::styled(format!("{} seeders", seeders), Style::default().fg(COLOR_GREEN)),
        ]));
    }

    let meta_para = Paragraph::new(meta_lines)
        .block(meta_block)
        .wrap(Wrap { trim: true });
    frame.render_widget(meta_para, top_split[1]);

    // Bottom Section: Overview & Stream URL
    let bottom_split = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(4),    // Plot Overview
            Constraint::Length(3), // Stream URL
        ])
        .split(showcase_chunks[1]);

    // 3. Overview Box
    let synopsis_text = selected
        .synopsis
        .as_deref()
        .unwrap_or("No plot overview available for this title.");

    let overview_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(COLOR_SURFACE2))
        .title(Span::styled(" 📖 Plot Overview ", Style::default().fg(COLOR_YELLOW).add_modifier(Modifier::BOLD)));

    let overview_para = Paragraph::new(synopsis_text)
        .style(Style::default().fg(COLOR_TEXT))
        .block(overview_block)
        .wrap(Wrap { trim: true });
    frame.render_widget(overview_para, bottom_split[0]);

    // 4. Stream URL Box
    let url_display = selected.download_url.as_deref().unwrap_or(&selected.url);
    let stream_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(COLOR_SURFACE2))
        .title(Span::styled(" ⚡ Stream Link (<Enter> Play • <Space> Preview • <c> Copy) ", Style::default().fg(COLOR_GREEN)));

    let stream_para = Paragraph::new(url_display)
        .style(Style::default().fg(COLOR_SUBTEXT0))
        .block(stream_block);
    frame.render_widget(stream_para, bottom_split[1]);
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
        Span::styled("<c>", Style::default().fg(COLOR_LAVENDER).add_modifier(Modifier::BOLD)),
        Span::styled(" Copy ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("</>", Style::default().fg(COLOR_YELLOW).add_modifier(Modifier::BOLD)),
        Span::styled(" Search ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("<Tab>", Style::default().fg(COLOR_TEAL).add_modifier(Modifier::BOLD)),
        Span::styled(" Filter ", Style::default().fg(COLOR_SUBTEXT0)),
        Span::styled("<q>", Style::default().fg(COLOR_RED).add_modifier(Modifier::BOLD)),
        Span::styled(" Quit", Style::default().fg(COLOR_SUBTEXT0)),
    ];

    let footer_layout = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(42),
            Constraint::Percentage(58),
        ])
        .split(area);

    let status_para = Paragraph::new(Line::from(vec![Span::raw(" "), status_span]));
    let shortcuts_para = Paragraph::new(Line::from(shortcuts_spans));

    frame.render_widget(status_para, footer_layout[0]);
    frame.render_widget(shortcuts_para, footer_layout[1]);
}
