use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{
        Block, BorderType, Borders, Cell, Paragraph, Row, Table, Tabs, Wrap,
    },
    Frame,
};
use ratatui_image::StatefulImage;
use ratatui_image::protocol::StatefulProtocol;
use crate::app::App;
use crate::models::ProviderFilter;

pub fn render_ui(frame: &mut Frame, app: &mut App) {
    let size = frame.area();

    // Overall vertical layout: Header, Tabs, Main Body, Footer
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // Search bar
            Constraint::Length(3), // Provider tabs
            Constraint::Min(10),   // Dual-pane content
            Constraint::Length(2), // Bottom status & shortcuts
        ])
        .split(size);

    render_search_bar(frame, app, chunks[0]);
    render_provider_tabs(frame, app, chunks[1]);
    render_body(frame, app, chunks[2]);
    render_footer(frame, app, chunks[3]);
}

fn render_search_bar(frame: &mut Frame, app: &App, area: Rect) {
    let border_color = if app.is_editing_search {
        Color::Rgb(0, 240, 255) // Vibrant Neon Cyan
    } else {
        Color::Rgb(98, 114, 164) // Muted purple/gray
    };

    let title_span = Span::styled(
        " 🔍 Anime & Media Quality Search Engine ",
        Style::default().fg(Color::Rgb(0, 240, 255)).add_modifier(Modifier::BOLD),
    );

    let prompt_span = if app.is_editing_search {
        Span::styled(" ❯ ", Style::default().fg(Color::Rgb(80, 250, 123)).add_modifier(Modifier::BOLD))
    } else {
        Span::styled(" ❯ ", Style::default().fg(Color::Rgb(98, 114, 164)))
    };

    let query_span = if app.query_input.is_empty() {
        if app.is_editing_search {
            Span::styled("Type title to search (e.g. imaria, overflow)...", Style::default().fg(Color::DarkGray))
        } else {
            Span::styled("Press '/' or Enter to search", Style::default().fg(Color::DarkGray))
        }
    } else {
        Span::styled(&app.query_input, Style::default().fg(Color::White).add_modifier(Modifier::BOLD))
    };

    let status_badge = if app.is_searching {
        Span::styled(
            " [ ⏳ Querying 6 Providers... ] ",
            Style::default().fg(Color::Rgb(241, 250, 140)).add_modifier(Modifier::BOLD),
        )
    } else if !app.all_results.is_empty() {
        Span::styled(
            format!(" [ {} Sources Found ] ", app.all_results.len()),
            Style::default().fg(Color::Rgb(80, 250, 123)),
        )
    } else {
        Span::raw("")
    };

    let search_line = Line::from(vec![prompt_span, query_span, Span::raw(" "), status_badge]);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color))
        .title(title_span);

    let paragraph = Paragraph::new(search_line).block(block);
    frame.render_widget(paragraph, area);
}

fn render_provider_tabs(frame: &mut Frame, app: &App, area: Rect) {
    let all_filters = ProviderFilter::all();
    let titles: Vec<Line> = all_filters
        .iter()
        .map(|f| {
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

            let label = if count > 0 {
                format!(" {} ({}) ", f.name(), count)
            } else {
                format!(" {} ", f.name())
            };

            Line::from(Span::raw(label))
        })
        .collect();

    let selected_index = all_filters
        .iter()
        .position(|f| f == &app.active_filter)
        .unwrap_or(0);

    let tabs = Tabs::new(titles)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(Style::default().fg(Color::Rgb(68, 71, 90)))
                .title(Span::styled(" Provider Filter [Tab] ", Style::default().fg(Color::Rgb(189, 147, 249)))),
        )
        .select(selected_index)
        .style(Style::default().fg(Color::DarkGray))
        .highlight_style(
            Style::default()
                .fg(Color::Rgb(0, 240, 255))
                .add_modifier(Modifier::BOLD)
                .add_modifier(Modifier::UNDERLINED),
        );

    frame.render_widget(tabs, area);
}

fn render_body(frame: &mut Frame, app: &mut App, area: Rect) {
    let dual_pane = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(48), // Results list
            Constraint::Percentage(52), // Artwork & details card
        ])
        .split(area);

    render_results_table(frame, app, dual_pane[0]);
    render_details_card(frame, app, dual_pane[1]);
}

fn render_results_table(frame: &mut Frame, app: &mut App, area: Rect) {
    let header_cells = [
        "Score", "Provider", "Title / Episode", "Res", "Codec", "Type",
    ]
    .iter()
    .map(|h| {
        Cell::from(Span::styled(
            *h,
            Style::default()
                .fg(Color::Rgb(189, 147, 249))
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

            let score_style = if r.score >= 85.0 {
                Style::default().fg(Color::Rgb(80, 250, 123)).add_modifier(Modifier::BOLD)
            } else if r.score >= 70.0 {
                Style::default().fg(Color::Rgb(241, 250, 140))
            } else {
                Style::default().fg(Color::Rgb(255, 121, 198))
            };
            let score_cell = Cell::from(Span::styled(format!("★ {:>2.0}", r.score), score_style));

            let prov_color = match r.provider.as_str() {
                "HentaiMama" => Color::Rgb(255, 184, 108),
                "MuchoHentai" => Color::Rgb(0, 240, 255),
                "Hanime" => Color::Rgb(255, 85, 85),
                "Nyaa" => Color::Rgb(80, 250, 123),
                "HentaiWorld" => Color::Rgb(189, 147, 249),
                _ => Color::White,
            };
            let prov_cell = Cell::from(Span::styled(format!("{:<10}", r.provider), Style::default().fg(prov_color)));

            let title_text = if let Some(ref ep) = r.episode {
                format!("{} [Ep {}]", r.title, ep)
            } else {
                r.title.clone()
            };
            let title_cell = Cell::from(Span::styled(title_text, Style::default().fg(Color::White)));

            let res_cell = Cell::from(Span::styled(&r.resolution, Style::default().fg(Color::Rgb(0, 240, 255))));
            let codec_cell = Cell::from(Span::styled(&r.codec, Style::default().fg(Color::DarkGray)));

            let del_style = if r.delivery == "Instant CDN" {
                Style::default().fg(Color::Rgb(80, 250, 123))
            } else {
                Style::default().fg(Color::Rgb(241, 250, 140))
            };
            let del_cell = Cell::from(Span::styled(
                if r.delivery == "Instant CDN" { "CDN" } else { "P2P" },
                del_style,
            ));

            let row = Row::new(vec![score_cell, prov_cell, title_cell, res_cell, codec_cell, del_cell]);
            if disp_idx == app.selected_filtered_idx {
                row.style(
                    Style::default()
                        .bg(Color::Rgb(40, 42, 54))
                        .add_modifier(Modifier::BOLD),
                )
            } else {
                row
            }
        })
        .collect();

    let widths = [
        Constraint::Length(7),
        Constraint::Length(12),
        Constraint::Min(20),
        Constraint::Length(7),
        Constraint::Length(8),
        Constraint::Length(6),
    ];

    let count_text = format!(" Results ({}) ", app.filtered_indices.len());
    let table = Table::new(rows, widths)
        .header(header)
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(Style::default().fg(Color::Rgb(68, 71, 90)))
                .title(Span::styled(count_text, Style::default().fg(Color::Rgb(0, 240, 255)))),
        )
        .highlight_symbol("▶ ");

    frame.render_stateful_widget(table, area, &mut app.table_state);
}

fn render_details_card(frame: &mut Frame, app: &mut App, area: Rect) {
    let Some(selected) = app.selected_result().cloned() else {
        let block = Block::default()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::default().fg(Color::Rgb(68, 71, 90)))
            .title(Span::styled(" Media Details & Preview ", Style::default().fg(Color::DarkGray)));
        let msg = Paragraph::new("Select a stream from the left table to inspect metadata and artwork.")
            .style(Style::default().fg(Color::DarkGray))
            .block(block);
        frame.render_widget(msg, area);
        return;
    };

    // Subdivide right pane: Top section (Artwork + Meta), Bottom section (Synopsis + Stream specs)
    let card_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(16), // Artwork + Header
            Constraint::Min(8),     // Specs + Plot Synopsis
        ])
        .split(area);

    // Split top into: Left (Artwork ~40%), Right (Official Meta ~60%)
    let top_split = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(42), // Artwork
            Constraint::Percentage(58), // Official Meta
        ])
        .split(card_chunks[0]);

    // 1. Render Artwork widget (Sixel raster)
    let art_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Rgb(0, 240, 255)))
        .title(Span::styled(" 🖼 HD Poster (Sixel) ", Style::default().fg(Color::Rgb(0, 240, 255))));

    let inner_art_area = art_block.inner(top_split[0]);
    frame.render_widget(art_block, top_split[0]);

    if let Some(ref mut protocol) = app.image_protocol {
        let image_widget = StatefulImage::<StatefulProtocol>::default();
        frame.render_stateful_widget(image_widget, inner_art_area, protocol);
    } else {
        let placeholder = Paragraph::new("\n\n  ⏳ Loading\n  Poster...")
            .style(Style::default().fg(Color::DarkGray));
        frame.render_widget(placeholder, inner_art_area);
    }

    // 2. Render Official Metadata
    let meta_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Rgb(68, 71, 90)))
        .title(Span::styled(" Official Metadata ", Style::default().fg(Color::Rgb(189, 147, 249))));

    let official_title = selected
        .official_title
        .as_deref()
        .unwrap_or(selected.title.as_str());

    let studio_str = selected.studio.as_deref().unwrap_or("Studio Unknown");
    let year_str = selected.year.map(|y| y.to_string()).unwrap_or_else(|| "N/A".to_string());
    let rating_str = selected
        .rating
        .map(|r| format!("★ {:.1} / 10", r / 10.0))
        .unwrap_or_else(|| "Not Rated".to_string());

    let mut meta_lines = vec![
        Line::from(vec![
            Span::styled("Title:  ", Style::default().fg(Color::DarkGray)),
            Span::styled(official_title, Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
        ]),
        Line::from(vec![
            Span::styled("Studio: ", Style::default().fg(Color::DarkGray)),
            Span::styled(studio_str, Style::default().fg(Color::Rgb(255, 184, 108))),
            Span::styled("  Year: ", Style::default().fg(Color::DarkGray)),
            Span::styled(year_str, Style::default().fg(Color::White)),
        ]),
        Line::from(vec![
            Span::styled("Score:  ", Style::default().fg(Color::DarkGray)),
            Span::styled(rating_str, Style::default().fg(Color::Rgb(80, 250, 123)).add_modifier(Modifier::BOLD)),
        ]),
    ];

    if !selected.genres.is_empty() {
        let genre_spans: Vec<Span> = selected
            .genres
            .iter()
            .take(4)
            .map(|g| Span::styled(format!(" [{}]", g), Style::default().fg(Color::Rgb(189, 147, 249))))
            .collect();
        let mut row = vec![Span::styled("Genres: ", Style::default().fg(Color::DarkGray))];
        row.extend(genre_spans);
        meta_lines.push(Line::from(row));
    }

    // Censorship badge
    let censo_style = match selected.censorship.to_lowercase().as_str() {
        "uncensored" => Style::default().fg(Color::Rgb(80, 250, 123)).add_modifier(Modifier::BOLD),
        "decensored" => Style::default().fg(Color::Rgb(0, 240, 255)).add_modifier(Modifier::BOLD),
        _ => Style::default().fg(Color::Rgb(241, 250, 140)),
    };
    meta_lines.push(Line::from(vec![
        Span::styled("Status: ", Style::default().fg(Color::DarkGray)),
        Span::styled(format!("[ {} ]", selected.censorship.to_uppercase()), censo_style),
    ]));

    let meta_para = Paragraph::new(meta_lines)
        .block(meta_block)
        .wrap(Wrap { trim: true });
    frame.render_widget(meta_para, top_split[1]);

    // 3. Render Specs & Synopsis (Bottom section)
    let bottom_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Rgb(68, 71, 90)))
        .title(Span::styled(" Stream Quality & Synopsis ", Style::default().fg(Color::Rgb(241, 250, 140))));

    let mut spec_lines = vec![
        Line::from(vec![
            Span::styled("Resolution: ", Style::default().fg(Color::DarkGray)),
            Span::styled(&selected.resolution, Style::default().fg(Color::Rgb(0, 240, 255))),
            Span::styled("  Codec: ", Style::default().fg(Color::DarkGray)),
            Span::styled(&selected.codec, Style::default().fg(Color::White)),
            Span::styled("  Audio: ", Style::default().fg(Color::DarkGray)),
            Span::styled(&selected.audio, Style::default().fg(Color::Rgb(255, 184, 108))),
        ]),
        Line::from(vec![
            Span::styled("Delivery:   ", Style::default().fg(Color::DarkGray)),
            Span::styled(&selected.delivery, Style::default().fg(Color::Rgb(80, 250, 123))),
            Span::styled("  Subs: ", Style::default().fg(Color::DarkGray)),
            Span::styled(&selected.subtitles, Style::default().fg(Color::White)),
        ]),
    ];

    if let Some(seeders) = selected.seeders {
        spec_lines.push(Line::from(vec![
            Span::styled("Seeders:    ", Style::default().fg(Color::DarkGray)),
            Span::styled(seeders.to_string(), Style::default().fg(Color::Rgb(80, 250, 123))),
            Span::styled("  Size: ", Style::default().fg(Color::DarkGray)),
            Span::styled(&selected.size, Style::default().fg(Color::White)),
        ]));
    }

    // Synopsis
    spec_lines.push(Line::from(""));
    let synopsis = selected.synopsis.as_deref().unwrap_or("No synopsis available for this title.");
    spec_lines.push(Line::from(Span::styled(synopsis, Style::default().fg(Color::DarkGray))));

    let bottom_para = Paragraph::new(spec_lines)
        .block(bottom_block)
        .wrap(Wrap { trim: true });
    frame.render_widget(bottom_para, card_chunks[1]);
}

fn render_footer(frame: &mut Frame, app: &App, area: Rect) {
    let status_span = Span::styled(&app.status_message, Style::default().fg(Color::White));

    let shortcuts_spans = vec![
        Span::styled("<Enter>", Style::default().fg(Color::Rgb(80, 250, 123)).add_modifier(Modifier::BOLD)),
        Span::styled(" Play  ", Style::default().fg(Color::DarkGray)),
        Span::styled("<Space>", Style::default().fg(Color::Rgb(0, 240, 255)).add_modifier(Modifier::BOLD)),
        Span::styled(" Preview  ", Style::default().fg(Color::DarkGray)),
        Span::styled("<d>", Style::default().fg(Color::Rgb(255, 184, 108)).add_modifier(Modifier::BOLD)),
        Span::styled(" Turbo Download  ", Style::default().fg(Color::DarkGray)),
        Span::styled("<c>", Style::default().fg(Color::Rgb(189, 147, 249)).add_modifier(Modifier::BOLD)),
        Span::styled(" Copy  ", Style::default().fg(Color::DarkGray)),
        Span::styled("</>", Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD)),
        Span::styled(" Search  ", Style::default().fg(Color::DarkGray)),
        Span::styled("<Tab>", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
        Span::styled(" Sources  ", Style::default().fg(Color::DarkGray)),
        Span::styled("<q>", Style::default().fg(Color::Red).add_modifier(Modifier::BOLD)),
        Span::styled(" Quit", Style::default().fg(Color::DarkGray)),
    ];

    let footer_layout = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(45),
            Constraint::Percentage(55),
        ])
        .split(area);

    let status_para = Paragraph::new(Line::from(vec![Span::raw(" "), status_span]));
    let shortcuts_para = Paragraph::new(Line::from(shortcuts_spans));

    frame.render_widget(status_para, footer_layout[0]);
    frame.render_widget(shortcuts_para, footer_layout[1]);
}
