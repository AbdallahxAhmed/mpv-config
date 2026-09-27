mod models;
mod bridge;
mod mpv;
mod app;
mod ui;

use std::io::stdout;
use std::time::Duration;
use anyhow::Result;
use crossterm::{
    event::{Event, KeyCode, KeyEventKind, KeyModifiers},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use futures_util::StreamExt;
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;
use tokio::sync::mpsc;
use app::{App, AppAction};

#[tokio::main]
async fn main() -> Result<()> {
    // Install panic hook to restore terminal on crash
    let original_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |panic_info| {
        let _ = disable_raw_mode();
        let _ = execute!(stdout(), LeaveAlternateScreen);
        original_hook(panic_info);
    }));

    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let (action_tx, mut action_rx) = mpsc::channel::<AppAction>(100);
    let mut app = App::new();

    // Check if initial query was passed via CLI args
    let args: Vec<String> = std::env::args().skip(1).collect();
    if !args.is_empty() {
        app.query_input = args.join(" ");
        app.start_search(action_tx.clone());
    }

    let mut event_stream = crossterm::event::EventStream::new();
    let mut tick_interval = tokio::time::interval(Duration::from_millis(33));

    while !app.should_quit {
        terminal.draw(|f| ui::render_ui(f, &mut app))?;

        tokio::select! {
            _ = tick_interval.tick() => {
                // Regular frame redraw
            }
            Some(action) = action_rx.recv() => {
                app.handle_action(action, action_tx.clone());
            }
            Some(Ok(event)) = event_stream.next() => {
                if let Event::Key(key) = event {
                    if key.kind == KeyEventKind::Press {
                        if app.is_editing_search {
                            match key.code {
                                KeyCode::Enter => {
                                    app.start_search(action_tx.clone());
                                }
                                KeyCode::Esc => {
                                    app.is_editing_search = false;
                                }
                                KeyCode::Backspace => {
                                    app.query_input.pop();
                                }
                                KeyCode::Char(c) => {
                                    if key.modifiers == KeyModifiers::CONTROL && c == 'c' {
                                        app.should_quit = true;
                                    } else {
                                        app.query_input.push(c);
                                    }
                                }
                                _ => {}
                            }
                        } else {
                            match key.code {
                                KeyCode::Char('q') | KeyCode::Esc => {
                                    app.should_quit = true;
                                }
                                KeyCode::Char('/') | KeyCode::Char('s') => {
                                    app.is_editing_search = true;
                                }
                                KeyCode::Up | KeyCode::Char('k') => {
                                    app.select_prev();
                                    app.trigger_image_load_for_selected(action_tx.clone());
                                }
                                KeyCode::Down | KeyCode::Char('j') => {
                                    app.select_next();
                                    app.trigger_image_load_for_selected(action_tx.clone());
                                }
                                KeyCode::Tab => {
                                    app.next_filter();
                                    app.trigger_image_load_for_selected(action_tx.clone());
                                }
                                KeyCode::BackTab => {
                                    app.prev_filter();
                                    app.trigger_image_load_for_selected(action_tx.clone());
                                }
                                KeyCode::Enter => {
                                    app.play_selected();
                                }
                                KeyCode::Char(' ') => {
                                    app.preview_selected();
                                }
                                KeyCode::Char('d') => {
                                    app.download_selected();
                                }
                                KeyCode::Char('p') => {
                                    app.toggle_artwork_mode(action_tx.clone());
                                }
                                KeyCode::Char('c') => {
                                    app.copy_selected_url();
                                }
                                _ => {}
                            }
                        }
                    }
                }
            }
        }
    }

    // Restore terminal
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;

    Ok(())
}
