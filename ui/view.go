package main

import (
	"fmt"
	"path"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/x/ansi"
)

const (
	indentPhase = "  "
	indentSub   = "      "
	maxBoxWidth = 74
)

// ─── small helpers ───────────────────────────────────────────────────

func fmtDuration(d time.Duration) string {
	if d < 0 {
		d = 0
	}
	if d < time.Minute {
		return fmt.Sprintf("%.1fs", d.Seconds())
	}
	return fmt.Sprintf("%dm %02ds", int(d.Minutes()), int(d.Seconds())%60)
}

func fmtClock(d time.Duration) string {
	s := int(d.Seconds())
	return fmt.Sprintf("%d:%02d", s/60, s%60)
}

func humanBytes(n int64) string {
	v := float64(n)
	for _, unit := range []string{"B", "KB", "MB", "GB"} {
		if v < 1024 || unit == "GB" {
			return fmt.Sprintf("%.1f %s", v, unit)
		}
		v /= 1024
	}
	return fmt.Sprintf("%.1f TB", v)
}

func (m *model) clamp(s string, width int) string {
	if width < 1 {
		width = 1
	}
	if ansi.StringWidth(s) <= width {
		return s
	}
	return ansi.Truncate(s, width, "…")
}

// spread places left and right on one row of the given width; the right part
// is dropped when it does not fit, the left part is truncated last.
func (m *model) spread(left, right string, width int) string {
	lw, rw := ansi.StringWidth(left), ansi.StringWidth(right)
	if right == "" || lw+rw+2 > width {
		return m.clamp(left, width)
	}
	return left + strings.Repeat(" ", width-lw-rw) + right
}

func (m *model) lineWidth() int {
	w := m.width
	if w <= 0 {
		w = defaultWidth
	}
	return w - 1 // never touch the last column: no auto-wrap smear
}

// ─── header / phases ─────────────────────────────────────────────────

func (m *model) renderHeader() string {
	left := indentPhase + m.st.Brand.Render("mpv-config")
	if m.command != "" {
		left += "  " + m.st.Subtle.Render(m.command)
	}
	return "\n" + m.spread(left, m.st.Faint.Render(m.osLabel), m.lineWidth()) + "\n"
}

func (m *model) phaseIcon(p *phase) string {
	switch p.status {
	case phaseActive:
		if m.prompt != nil {
			return m.st.Accent.Render(m.g.Prompt)
		}
		return m.st.Accent.Render(m.g.Spinner[m.frame%len(m.g.Spinner)])
	case phaseDone:
		return m.st.OK.Render(m.g.OK)
	case phaseFailed:
		return m.st.Fail.Render(m.g.Fail)
	case phaseSkipped:
		return m.st.Faint.Render(m.g.Pending)
	default:
		return m.st.Faint.Render(m.g.Pending)
	}
}

func (m *model) phaseRow(p *phase) string {
	title := p.title
	var titleStyled string
	switch p.status {
	case phaseActive:
		titleStyled = m.st.Bold.Render(title)
	case phaseFailed:
		titleStyled = m.st.Fail.Render(title)
	case phaseDone:
		titleStyled = m.st.Text.Render(title)
	default:
		titleStyled = m.st.Faint.Render(title)
	}
	left := indentPhase + m.phaseIcon(p) + " " + titleStyled
	var right []string
	if p.note != "" {
		right = append(right, m.st.Subtle.Render(p.note))
	}
	switch p.status {
	case phaseActive:
		right = append(right, m.st.Faint.Render(fmtDuration(m.now().Sub(p.start))))
	case phaseDone, phaseFailed:
		right = append(right, m.st.Faint.Render(fmtDuration(p.end.Sub(p.start))))
	case phaseSkipped:
		right = append(right, m.st.Faint.Render("skipped"))
	}
	return m.spread(left, strings.Join(right, "  "), m.lineWidth())
}

func (m *model) renderCommitted(p *phase) string {
	rows := []string{m.phaseRow(p)}
	for _, line := range p.lines {
		rows = append(rows, m.clamp(indentSub+line, m.lineWidth()))
	}
	return strings.Join(rows, "\n")
}

// ─── live area ───────────────────────────────────────────────────────

func (m *model) View() string {
	if m.stats != nil {
		m.stats.views++
	}
	if m.finished || m.suspended {
		return ""
	}
	w := m.lineWidth()
	var b strings.Builder
	write := func(s string) {
		b.WriteString(m.clamp(s, w))
		b.WriteByte('\n')
	}
	for _, p := range m.phases {
		if p.status == phaseDone || p.status == phaseFailed || p.status == phaseSkipped {
			continue
		}
		write(m.phaseRow(p))
		if p.status != phaseActive {
			continue
		}
		recent := p.lines
		if len(recent) > liveKeptLines {
			recent = recent[len(recent)-liveKeptLines:]
		}
		for _, line := range recent {
			write(indentSub + line)
		}
		if m.spinner != "" {
			write(indentSub + m.st.Subtle.Render(m.spinner))
		}
		for _, t := range m.transfers {
			write(indentSub + m.transferRow(t, w-len(indentSub)))
		}
		for _, c := range m.commands {
			left := indentSub + m.st.Key.Render("$ ") + m.st.Subtle.Render(c.text)
			write(m.spread(left, m.st.Faint.Render(fmtClock(m.now().Sub(c.started))), w))
		}
		if m.prompt == nil {
			for _, line := range m.live {
				write(indentSub + m.st.Faint.Render(m.g.Info+" "+line))
			}
		} else {
			for _, line := range m.renderPrompt() {
				write(line)
			}
		}
	}
	b.WriteByte('\n')
	b.WriteString(m.footer(w))
	return b.String()
}

func (m *model) footer(w int) string {
	if m.prompt != nil {
		var hint string
		if m.prompt.kind == "menu" {
			hint = fmt.Sprintf("↑/↓ move · enter select · 1-%d pick · esc keeps %s",
				min(9, len(m.prompt.items)), m.prompt.items[m.prompt.def].Value)
		} else {
			hint = "y/n · ←/→ · enter confirm"
		}
		return m.clamp(indentPhase+m.st.Faint.Render(hint), w)
	}
	elapsed := m.st.Faint.Render(fmtClock(m.now().Sub(m.started)))
	switch m.cancelling {
	case 0:
		return m.spread(indentPhase+m.st.Faint.Render("ctrl+c cancel"), elapsed, w)
	case 1:
		return m.spread(indentPhase+m.st.Warn.Render("Cancelling — rolling back safely…")+
			m.st.Faint.Render("  ctrl+c again to force"), elapsed, w)
	default:
		return m.spread(indentPhase+m.st.Fail.Render("Force-stopping…"), elapsed, w)
	}
}

func (m *model) transferRow(t *transfer, w int) string {
	label := strings.TrimPrefix(t.label, "Downloading ")
	if len([]rune(label)) > 30 {
		label = string([]rune(label)[:29]) + "…"
	}
	icon := m.st.Key.Render(m.g.Action["fetch"])
	if t.state == "connect" || t.state == "" {
		return icon + " " + m.st.Text.Render(label) + "  " +
			m.st.Faint.Render("connecting "+m.g.Spinner[m.frame%len(m.g.Spinner)])
	}
	elapsed := m.now().Sub(t.started).Seconds()
	speed := ""
	if elapsed > 0.2 {
		speed = humanBytes(int64(float64(t.done)/elapsed)) + "/s"
	}
	if t.total <= 0 || t.done > t.total {
		return icon + " " + m.st.Text.Render(label) + "  " +
			m.st.Subtle.Render(humanBytes(t.done)+"  "+speed)
	}
	pct := float64(t.done) / float64(t.total)
	stats := fmt.Sprintf("%3d%%  %s/%s", int(pct*100), humanBytes(t.done), humanBytes(t.total))
	if speed != "" {
		stats += "  " + speed
	}
	fixed := 2 + ansi.StringWidth(label) + 2 + 2 + len(stats)
	barW := w - fixed
	if barW > maxBarWidth {
		barW = maxBarWidth
	}
	row := icon + " " + m.st.Text.Render(label) + "  "
	if barW >= minBarWidth {
		m.bar.Width = barW
		row += m.bar.ViewAs(pct) + "  "
	}
	return row + m.st.Subtle.Render(stats)
}

func (m *model) renderPrompt() []string {
	p := m.prompt
	head := indentSub + m.st.Accent.Render(m.g.Prompt) + " " + m.st.Bold.Render(p.text)
	if p.kind == "confirm" {
		opt := func(label string, on bool) string {
			if on {
				return m.st.Accent.Render(m.g.Pointer + " " + label)
			}
			return m.st.Faint.Render("  " + label)
		}
		return []string{head + "   " + opt("Yes", p.cursor == 0) + "  " + opt("No", p.cursor == 1)}
	}
	rows := []string{head}
	valueW := 0
	for _, it := range p.items {
		valueW = max(valueW, ansi.StringWidth(it.Value))
	}
	for i, it := range p.items {
		num := fmt.Sprintf("%d", i+1)
		value := it.Value + strings.Repeat(" ", valueW-ansi.StringWidth(it.Value))
		if i == p.cursor {
			rows = append(rows, indentSub+"  "+m.st.Accent.Render(m.g.Pointer+" "+num+"  "+value)+
				"  "+m.st.Text.Render(it.Label))
		} else {
			rows = append(rows, indentSub+"    "+m.st.Faint.Render(num+"  ")+m.st.Subtle.Render(value)+
				"  "+m.st.Faint.Render(it.Label))
		}
	}
	return rows
}

// ─── persistent blocks: tables, plan, outcome ────────────────────────

func (m *model) renderTable(ev Event) []string {
	if len(ev.Columns) == 0 || len(ev.Rows) == 0 {
		return nil
	}
	status := -1
	for i, c := range ev.Columns {
		if strings.EqualFold(c, "status") {
			status = i
		}
	}
	if status >= 0 {
		// Verification-style tables: every passing row is noise once it
		// passed. Count them on the phase; list only what needs attention.
		var lines []string
		passed, skipped := 0, 0
		for _, row := range ev.Rows {
			if status >= len(row) {
				continue
			}
			state := strings.ToUpper(strings.TrimSpace(row[status]))
			rest := make([]string, 0, len(row))
			for i, cell := range row {
				if i != status && strings.TrimSpace(cell) != "" {
					rest = append(rest, cell)
				}
			}
			name, detail := strings.Join(rest, ""), ""
			if len(rest) > 1 {
				name, detail = rest[0], strings.Join(rest[1:], " · ")
			}
			switch state {
			case "OK":
				passed++
			case "SKIPPED":
				skipped++
			default:
				lines = append(lines, m.st.Fail.Render(m.g.Fail)+" "+m.st.Text.Render(name)+m.dimSuffix(detail))
			}
		}
		note := fmt.Sprintf("%d/%d checks passed", passed, passed+len(lines))
		if skipped > 0 {
			note += fmt.Sprintf(" · %d skipped", skipped)
		}
		m.ensurePhase().note = note
		return lines
	}
	if len(ev.Columns) == 2 {
		keyW := 0
		for _, row := range ev.Rows {
			if len(row) > 0 {
				keyW = max(keyW, ansi.StringWidth(row[0]))
			}
		}
		keyW = min(keyW, 18)
		var lines []string
		for _, row := range ev.Rows {
			if len(row) < 2 {
				continue
			}
			key := m.clamp(row[0], keyW)
			key += strings.Repeat(" ", keyW-ansi.StringWidth(key))
			lines = append(lines, m.st.Subtle.Render(key)+"  "+m.st.Text.Render(row[1]))
		}
		return lines
	}
	widths := make([]int, len(ev.Columns))
	for _, row := range append([][]string{ev.Columns}, ev.Rows...) {
		for i := 0; i < len(row) && i < len(widths); i++ {
			widths[i] = min(max(widths[i], ansi.StringWidth(row[i])), 36)
		}
	}
	format := func(row []string, style lipgloss.Style) string {
		cells := make([]string, 0, len(widths))
		for i := range widths {
			cell := ""
			if i < len(row) {
				cell = m.clamp(row[i], widths[i])
			}
			cells = append(cells, cell+strings.Repeat(" ", widths[i]-ansi.StringWidth(cell)))
		}
		return style.Render(strings.TrimRight(strings.Join(cells, "  "), " "))
	}
	lines := []string{}
	if ev.Title != "" {
		lines = append(lines, m.st.Bold.Render(ev.Title))
	}
	lines = append(lines, format(ev.Columns, m.st.Subtle))
	for _, row := range ev.Rows {
		lines = append(lines, format(row, m.st.Text))
	}
	return lines
}

func (m *model) actionStyle(action string) lipgloss.Style {
	switch action {
	case "install", "create", "deploy":
		return m.st.OK
	case "refresh":
		return m.st.Warn
	case "fetch":
		return m.st.Key
	case "remove":
		return m.st.Fail
	case "backup":
		return m.st.Accent
	}
	return m.st.Subtle
}

func (m *model) renderPlan(ev Event) []string {
	labelW := 0
	for _, g := range ev.Groups {
		labelW = max(labelW, ansi.StringWidth(g.Label))
	}
	labelW = min(labelW, 16)
	avail := m.lineWidth() - len(indentSub) - labelW - 2
	var lines []string
	for _, g := range ev.Groups {
		var parts []string
		unchanged := 0
		for _, e := range g.Entries {
			if e.Action == "skip" {
				unchanged++
				continue
			}
			name := strings.TrimRight(e.Target, "/")
			if strings.Contains(name, "/") && len(g.Entries) > 2 {
				name = path.Base(name) // many files in one dir: names suffice
			}
			icon := m.g.Action[e.Action]
			if icon == "" {
				icon = m.g.Bullet
			}
			parts = append(parts, m.actionStyle(e.Action).Render(icon)+" "+m.st.Text.Render(name))
		}
		tail := ""
		if unchanged > 0 {
			tail = m.st.Faint.Render(fmt.Sprintf("  %d unchanged", unchanged))
		}
		sep := m.st.Faint.Render(" · ")
		body := ""
		for i, part := range parts {
			more := ""
			if left := len(parts) - i - 1; left > 0 {
				more = m.st.Faint.Render(fmt.Sprintf(" · +%d more", left))
			}
			candidate := body
			if candidate != "" {
				candidate += sep
			}
			candidate += part
			if ansi.StringWidth(candidate+more+tail) > avail && body != "" {
				body += m.st.Faint.Render(fmt.Sprintf(" · +%d more", len(parts)-i))
				break
			}
			body = candidate
		}
		if body == "" {
			body = m.st.Faint.Render("nothing to do")
		}
		label := m.clamp(g.Label, labelW)
		label += strings.Repeat(" ", labelW-ansi.StringWidth(label))
		lines = append(lines, m.st.Subtle.Render(label)+"  "+body+tail)
	}
	return lines
}

func (m *model) box(border lipgloss.TerminalColor, lines []string) string {
	b := lipgloss.NormalBorder()
	if m.g.Rounded {
		b = lipgloss.RoundedBorder()
	}
	width := min(maxBoxWidth, m.lineWidth()-len(indentPhase)-2)
	inner := width - 4
	for i, l := range lines {
		lines[i] = m.clamp(l, inner)
	}
	style := lipgloss.NewStyle().Border(b).BorderForeground(border).Padding(0, 1).Width(width - 2)
	boxed := style.Render(strings.Join(lines, "\n"))
	rows := strings.Split(boxed, "\n")
	for i := range rows {
		rows[i] = indentPhase + rows[i]
	}
	return strings.Join(rows, "\n")
}

func (m *model) panelLines(icon string, iconStyle lipgloss.Style, text string) []string {
	var lines []string
	for i, raw := range strings.Split(strings.TrimSpace(text), "\n") {
		raw = strings.TrimSpace(raw)
		if raw == "" {
			continue
		}
		if i == 0 {
			lines = append(lines, iconStyle.Render(icon)+"  "+m.st.Bold.Render(strings.TrimSuffix(raw, ".")))
			continue
		}
		if k, v, ok := strings.Cut(raw, ": "); ok && len(k) <= 14 {
			lines = append(lines, "   "+m.st.Subtle.Render(fmt.Sprintf("%-8s", k))+" "+m.st.Text.Render(v))
		} else {
			lines = append(lines, "   "+m.st.Text.Render(raw))
		}
	}
	return lines
}

func (m *model) renderOutcome() string {
	var out []string
	elapsed := fmtDuration(m.now().Sub(m.started))
	meta := []string{"Finished in " + elapsed}
	switch {
	case m.exitCode == 0:
		text := "Done"
		if m.lastInfo != "" {
			text = m.lastInfo // e.g. the dry-run notice: the run's real conclusion
		}
		if m.panel != nil && strings.TrimSpace(m.panel.Text) != "" {
			text = m.panel.Text
		}
		out = append(out, "", m.box(colOK, m.panelLines(m.g.OK, m.st.OK, text)))
	case m.exitCode == 130 || m.cancelling > 0:
		meta[0] = "Stopped after " + elapsed
		lines := m.panelLines(m.g.Warn, m.st.Warn, "Cancelled")
		lines = append(lines, "   "+m.st.Subtle.Render("Interrupted operations are rolled back; backups are kept."))
		out = append(out, "", m.box(colWarn, lines))
	default:
		verb := "Command"
		if m.command != "" {
			verb = strings.ToUpper(m.command[:1]) + m.command[1:]
		}
		lines := m.panelLines(m.g.Fail, m.st.Fail, verb+" failed")
		shown := m.errors
		if len(shown) > 3 {
			shown = shown[len(shown)-3:]
		}
		inner := min(maxBoxWidth, m.lineWidth()-len(indentPhase)-2) - 4
		for _, e := range shown {
			// Error text is the one thing worth reading in full: wrap it.
			for _, part := range strings.Split(ansi.Wrap(e, inner-3, " /"), "\n") {
				lines = append(lines, "   "+m.st.Text.Render(part))
			}
		}
		tail := m.stderrTail
		if len(tail) > 8 {
			tail = tail[len(tail)-8:]
		}
		for _, t := range tail {
			lines = append(lines, "   "+m.st.Faint.Render(t))
		}
		out = append(out, "", m.box(colFail, lines))
		meta[0] = fmt.Sprintf("Exit code %d after %s", m.exitCode, elapsed)
	}
	if m.warnings > 0 {
		meta = append(meta, fmt.Sprintf("%d warning%s", m.warnings, map[bool]string{true: "", false: "s"}[m.warnings == 1]))
	}
	if path := m.log.path(); path != "" {
		meta = append(meta, "log "+path)
	}
	out = append(out, m.clamp(indentPhase+" "+m.st.Faint.Render(strings.Join(meta, " · ")), m.lineWidth()), "")
	return strings.Join(out, "\n")
}
