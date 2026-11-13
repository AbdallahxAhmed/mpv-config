package main

import (
	"os"
	"runtime"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// Glyphs differ by terminal capability, never by OS alone: Windows Terminal,
// VS Code and every modern Linux/macOS emulator get the rich set; the legacy
// Windows console host (Consolas has no braille or check marks) and the Linux
// virtual console get a set that every bundled font can draw.
type Glyphs struct {
	OK, Fail, Warn, Info, Pending, Prompt, Pointer, Bullet, Arrow, Pipe string
	Spinner                                                             []string
	BarFull, BarEmpty                                                   rune
	Rounded                                                             bool
	Action                                                              map[string]string
}

var richGlyphs = Glyphs{
	OK: "✓", Fail: "✗", Warn: "!", Info: "·", Pending: "○", Prompt: "?",
	Pointer: "▸", Bullet: "•", Arrow: "→", Pipe: "│",
	Spinner: []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"},
	BarFull: '━', BarEmpty: '─', Rounded: true,
	Action: map[string]string{
		"install": "+", "create": "+", "refresh": "↻", "fetch": "↓",
		"deploy": "→", "remove": "−", "backup": "⊙", "skip": "=",
	},
}

// basicGlyphs only uses code page 437 characters: Consolas (the legacy
// Windows console font) and the default Linux console fonts all carry them.
var basicGlyphs = Glyphs{
	OK: "√", Fail: "×", Warn: "!", Info: "·", Pending: "○", Prompt: "?",
	Pointer: "►", Bullet: "•", Arrow: "→", Pipe: "│",
	Spinner: []string{"|", "/", "-", "\\"},
	BarFull: '█', BarEmpty: '░', Rounded: false,
	Action: map[string]string{
		"install": "+", "create": "+", "refresh": "~", "fetch": "↓",
		"deploy": "→", "remove": "-", "backup": "≡", "skip": "=",
	},
}

func detectGlyphs(getenv func(string) string, goos string) Glyphs {
	switch strings.ToLower(getenv("MPV_CONFIG_UI_GLYPHS")) {
	case "rich":
		return richGlyphs
	case "basic", "ascii":
		return basicGlyphs
	}
	if getenv("TERM") == "linux" {
		return basicGlyphs
	}
	if goos == "windows" {
		// WT_SESSION: Windows Terminal; TERM_PROGRAM: VS Code, WezTerm,
		// Hyper; ConEmuANSI: ConEmu/Cmder. Anything else is conhost.
		if getenv("WT_SESSION") == "" && getenv("TERM_PROGRAM") == "" && getenv("ConEmuANSI") != "ON" {
			return basicGlyphs
		}
	}
	return richGlyphs
}

func currentGlyphs() Glyphs { return detectGlyphs(os.Getenv, runtime.GOOS) }

// Palette: one violet accent (the mpv logo hue) fading to cyan in progress
// bars; semantic colors for state only. Adaptive so light themes stay legible.
var (
	colAccent  = lipgloss.AdaptiveColor{Light: "#6D28D9", Dark: "#A78BFA"}
	colAccent2 = lipgloss.AdaptiveColor{Light: "#0E7490", Dark: "#67E8F9"}
	colOK      = lipgloss.AdaptiveColor{Light: "#15803D", Dark: "#4ADE80"}
	colWarn    = lipgloss.AdaptiveColor{Light: "#B45309", Dark: "#FBBF24"}
	colFail    = lipgloss.AdaptiveColor{Light: "#B91C1C", Dark: "#F87171"}
	colMuted   = lipgloss.AdaptiveColor{Light: "#6B7280", Dark: "#7C8494"}
	colFaint   = lipgloss.AdaptiveColor{Light: "#9CA3AF", Dark: "#4B5263"}
	colText    = lipgloss.AdaptiveColor{Light: "#111827", Dark: "#E5E7EB"}

	gradientFrom = "#8B5CF6"
	gradientTo   = "#22D3EE"
)

type Styles struct {
	Brand, Subtle, Faint, Text, Bold, Accent, OK, Warn, Fail, Key lipgloss.Style
}

func newStyles() Styles {
	base := lipgloss.NewStyle()
	return Styles{
		Brand: base.Bold(true).Foreground(lipgloss.AdaptiveColor{Light: "#FFFFFF", Dark: "#0B0B12"}).
			Background(colAccent).Padding(0, 1),
		Subtle: base.Foreground(colMuted),
		Faint:  base.Foreground(colFaint),
		Text:   base.Foreground(colText),
		Bold:   base.Bold(true).Foreground(colText),
		Accent: base.Foreground(colAccent).Bold(true),
		OK:     base.Foreground(colOK).Bold(true),
		Warn:   base.Foreground(colWarn).Bold(true),
		Fail:   base.Foreground(colFail).Bold(true),
		Key:    base.Foreground(colAccent2),
	}
}
