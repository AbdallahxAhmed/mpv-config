package main

import (
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/progress"
	tea "github.com/charmbracelet/bubbletea"
)

type phaseStatus int

const (
	phasePending phaseStatus = iota
	phaseActive
	phaseDone
	phaseFailed
	phaseSkipped
)

type phase struct {
	key, title string
	status     phaseStatus
	start, end time.Time
	note       string
	lines      []string // persistent sub-lines, already styled
	errorTexts []string // raw error texts, to avoid listing a failure twice
}

type transfer struct {
	id           int
	label, state string
	done, total  int64
	started      time.Time
}

type runningCommand struct {
	id      int
	text    string
	started time.Time
}

type prompt struct {
	id     int
	kind   string // "confirm" | "menu"
	text   string
	items  []MenuItem
	cursor int
	def    int
}

type tickMsg time.Time

type sudoDoneMsg struct {
	id int
	ok bool
}

// interruptMsg: Ctrl+C (key) or an OS signal. fromSignal tells whether the
// child already received the same signal from the terminal.
type interruptMsg struct{ fromSignal bool }

const (
	liveLogLines  = 3
	liveKeptLines = 6
	stderrKeep    = 40
	tickInterval  = 100 * time.Millisecond
	minBarWidth   = 10
	maxBarWidth   = 32
	defaultWidth  = 80
	maxPlanInline = 5
)

type model struct {
	src     Source
	g       Glyphs
	st      Styles
	bar     progress.Model
	width   int
	command string
	osLabel string
	started time.Time
	now     func() time.Time
	log     *runLog

	phases    []*phase
	prints    []string
	live      []string
	transfers []*transfer
	commands  []*runningCommand
	spinner   string
	prompt    *prompt
	frame     int

	panel      *Event
	lastInfo   string
	errors     []string
	stderrTail []string
	warnings   int

	cancelling int
	suspended  bool // sudo owns the terminal: draw nothing
	finished   bool
	exitCode   int
	stats      *renderStats
}

func newModel(src Source, command, osLabel string, g Glyphs, log *runLog) *model {
	bar := progress.New(
		progress.WithGradient(gradientFrom, gradientTo),
		progress.WithoutPercentage(),
		progress.WithFillCharacters(g.BarFull, g.BarEmpty),
	)
	bar.EmptyColor = "#3A3F4B"
	return &model{
		src: src, g: g, st: newStyles(), bar: bar, width: defaultWidth,
		command: command, osLabel: osLabel, started: time.Now(), now: time.Now, log: log,
	}
}

func tick() tea.Cmd {
	return tea.Tick(tickInterval, func(t time.Time) tea.Msg { return tickMsg(t) })
}

func (m *model) Init() tea.Cmd {
	return tea.Batch(tea.Println(m.renderHeader()), tick())
}

// ─── Phase bookkeeping ───────────────────────────────────────────────

func (m *model) activePhase() *phase {
	for _, p := range m.phases {
		if p.status == phaseActive {
			return p
		}
	}
	return nil
}

// commitPhase closes p and queues it for the scrollback above the live area,
// where it never has to be redrawn again. Queued blocks leave in ONE ordered
// print per update (tea.Batch would run separate prints concurrently).
func (m *model) commitPhase(p *phase, status phaseStatus) {
	if p.status == phaseDone || p.status == phaseFailed || p.status == phaseSkipped {
		return
	}
	if status != phaseSkipped {
		p.end = m.now()
	}
	p.status = status
	m.prints = append(m.prints, m.renderCommitted(p))
}

// withPrints prepends the queued scrollback blocks to cmd, in order.
func (m *model) withPrints(cmd tea.Cmd) tea.Cmd {
	if len(m.prints) == 0 {
		return cmd
	}
	print := tea.Println(strings.Join(m.prints, "\n"))
	m.prints = nil
	if cmd == nil {
		return print
	}
	return tea.Sequence(print, cmd)
}

func (m *model) ensurePhase() *phase {
	if p := m.activePhase(); p != nil {
		return p
	}
	title := "Preparing"
	if m.command != "" {
		title = strings.ToUpper(m.command[:1]) + m.command[1:]
	}
	p := &phase{key: "_implicit", title: title, status: phaseActive, start: m.now()}
	m.phases = append(m.phases, p)
	return p
}

func (m *model) startPhase(key, title string) {
	activeIdx := -1
	for i, p := range m.phases {
		if p.status == phaseActive {
			activeIdx = i
			m.commitPhase(p, phaseDone)
		}
	}
	target := -1
	if key != "" {
		for i, p := range m.phases {
			if p.key == key && p.status == phasePending {
				target = i
				break
			}
		}
	}
	if target >= 0 {
		// Outline steps jumped over (e.g. a prompt skipped by --yes) read as
		// skipped, in order, so the scrollback stays a faithful checklist.
		for i := 0; i < target; i++ {
			if m.phases[i].status == phasePending {
				m.commitPhase(m.phases[i], phaseSkipped)
			}
		}
		p := m.phases[target]
		p.status, p.start = phaseActive, m.now()
		if p.title == "" {
			p.title = title
		}
	} else {
		p := &phase{key: key, title: title, status: phaseActive, start: m.now()}
		insert := activeIdx + 1
		m.phases = append(m.phases, nil)
		copy(m.phases[insert+1:], m.phases[insert:])
		m.phases[insert] = p
	}
	m.live, m.transfers, m.commands, m.spinner = nil, nil, nil, ""
}

func (m *model) addLive(line string) {
	m.live = append(m.live, line)
	if len(m.live) > liveLogLines {
		m.live = m.live[len(m.live)-liveLogLines:]
	}
}

func (m *model) persist(line string) {
	p := m.ensurePhase()
	p.lines = append(p.lines, line)
}

// ─── Update ──────────────────────────────────────────────────────────

func (m *model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	if batch, ok := msg.(batchMsg); ok {
		// Many events, one View(): the renderer cost no longer scales with
		// how chatty the deployer is.
		var cmds []tea.Cmd
		for _, item := range batch {
			if c := m.update(item); c != nil {
				cmds = append(cmds, c)
			}
		}
		if len(cmds) > 0 {
			cmd = tea.Sequence(cmds...)
		}
	} else {
		cmd = m.update(msg)
	}
	return m, m.withPrints(cmd)
}

func (m *model) update(msg tea.Msg) tea.Cmd {
	_, cmd := m.updateOne(msg)
	return cmd
}

func (m *model) updateOne(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		return m, nil
	case tickMsg:
		m.frame++
		if m.finished {
			return m, nil
		}
		return m, tick()
	case tea.KeyMsg:
		return m.handleKey(msg)
	case interruptMsg:
		return m, m.interrupt(msg.fromSignal)
	case eventMsg:
		m.log.event(msg.ev)
		return m, m.handleEvent(msg.ev)
	case lineMsg:
		m.log.line(msg.text, msg.stderr)
		text := strings.TrimRight(msg.text, " \t")
		if strings.TrimSpace(text) == "" {
			return m, nil
		}
		if msg.stderr {
			m.stderrTail = append(m.stderrTail, text)
			if len(m.stderrTail) > stderrKeep {
				m.stderrTail = m.stderrTail[len(m.stderrTail)-stderrKeep:]
			}
		}
		m.addLive(text)
		return m, nil
	case sudoDoneMsg:
		m.suspended = false
		m.src.Reply(msg.id, msg.ok)
		if !msg.ok {
			m.persist(m.st.Warn.Render(m.g.Warn) + " " + m.st.Text.Render("administrator password was not accepted"))
		}
		return m, nil
	case childExitMsg:
		return m, m.finish(msg.code)
	}
	return m, nil
}

func (m *model) interrupt(fromSignal bool) tea.Cmd {
	if m.finished {
		return nil
	}
	m.cancelling++
	if m.cancelling == 1 {
		if !fromSignal || !signalReachesChild {
			m.src.Interrupt()
		}
		if m.prompt != nil {
			m.prompt = nil
		}
		return nil
	}
	m.src.Kill()
	return nil
}

func (m *model) handleKey(k tea.KeyMsg) (tea.Model, tea.Cmd) {
	key := k.String()
	if key == "ctrl+c" {
		return m, m.interrupt(false)
	}
	p := m.prompt
	if p == nil {
		return m, nil
	}
	answer := func(value any, shown string) (tea.Model, tea.Cmd) {
		m.src.Reply(p.id, value)
		m.prompt = nil
		if ph := m.activePhase(); p.kind == "menu" && ph != nil && ph.note == "" {
			// A choice IS the phase's outcome: show it on the phase row.
			ph.note = shown
			return m, nil
		}
		m.persist(m.st.Accent.Render(m.g.Prompt) + " " + m.st.Text.Render(p.text) + "  " +
			m.st.Key.Render(shown))
		return m, nil
	}
	switch p.kind {
	case "confirm":
		switch key {
		case "y", "Y":
			return answer(true, "yes")
		case "n", "N", "esc":
			return answer(false, "no")
		case "left", "right", "tab", "h", "l":
			p.cursor = 1 - p.cursor
		case "enter":
			return answer(p.cursor == 0, map[bool]string{true: "yes", false: "no"}[p.cursor == 0])
		}
	case "menu":
		switch key {
		case "up", "k":
			p.cursor = (p.cursor - 1 + len(p.items)) % len(p.items)
		case "down", "j", "tab":
			p.cursor = (p.cursor + 1) % len(p.items)
		case "enter":
			return answer(p.items[p.cursor].Value, p.items[p.cursor].Value)
		case "esc":
			return answer(p.items[p.def].Value, p.items[p.def].Value)
		default:
			if len(key) == 1 && key[0] >= '1' && key[0] <= '9' {
				if i := int(key[0] - '1'); i < len(p.items) {
					return answer(p.items[i].Value, p.items[i].Value)
				}
			}
		}
	}
	return m, nil
}

func (m *model) handleEvent(ev Event) tea.Cmd {
	switch ev.T {
	case "hello":
		if ev.Command != "" {
			m.command = ev.Command
		}
	case "outline":
		for _, s := range ev.Steps {
			m.phases = append(m.phases, &phase{key: s.Key, title: s.Title, status: phasePending})
		}
	case "phase":
		m.startPhase(ev.Key, ev.Title)
	case "log":
		m.handleLog(ev)
	case "table":
		for _, line := range m.renderTable(ev) {
			m.persist(line)
		}
	case "plan":
		for _, line := range m.renderPlan(ev) {
			m.persist(line)
		}
	case "summary":
		p := m.ensurePhase()
		parts := []string{}
		if ev.Succeeded > 0 {
			parts = append(parts, fmt.Sprintf("%d ok", ev.Succeeded))
		}
		if ev.Skipped > 0 {
			parts = append(parts, fmt.Sprintf("%d skipped", ev.Skipped))
		}
		if len(ev.Failed) > 0 {
			parts = append(parts, fmt.Sprintf("%d failed", len(ev.Failed)))
		}
		if len(parts) > 0 {
			p.note = strings.Join(parts, " · ")
		}
		for _, f := range ev.Failed {
			if m.alreadyReported(p, f.Name) {
				continue // the component printed its own error line already
			}
			m.persist(m.st.Fail.Render(m.g.Fail) + " " + m.st.Text.Render(f.Name) +
				m.dimSuffix(f.Detail))
		}
	case "progress":
		m.handleProgress(ev)
	case "command":
		m.handleCommand(ev)
	case "spinner":
		if ev.State == "start" {
			m.spinner = ev.Text
		} else {
			m.spinner = ""
		}
	case "panel":
		e := ev
		m.panel = &e
	case "prompt":
		p := &prompt{id: ev.ID, kind: ev.Kind, text: ev.Text, items: ev.Items}
		if ev.Kind == "menu" {
			if len(p.items) == 0 {
				m.src.Reply(ev.ID, nil)
				return nil
			}
			var def int
			_ = json.Unmarshal(ev.Default, &def)
			if def < 0 || def >= len(p.items) {
				def = 0
			}
			p.def, p.cursor = def, def
		} else {
			var def = true
			_ = json.Unmarshal(ev.Default, &def)
			if !def {
				p.cursor = 1
			}
		}
		m.prompt = p
	case "sudo":
		id := ev.ID
		reason := ev.Reason
		notice := m.st.Warn.Render("  "+m.g.Prompt) + " " +
			m.st.Text.Render("Administrator access needed") + m.dimSuffix(reason)
		// Blank the live area first so the frame does not linger above
		// sudo's password prompt while the terminal is handed over.
		m.suspended = true
		return tea.Sequence(
			tea.Println(notice),
			tea.ExecProcess(exec.Command("sudo", "-v"), func(err error) tea.Msg {
				return sudoDoneMsg{id: id, ok: err == nil}
			}),
		)
	}
	return nil
}

func (m *model) handleLog(ev Event) {
	text := ev.Text
	switch ev.Level {
	case "ok":
		m.persist(m.st.OK.Render(m.g.OK) + " " + m.st.Subtle.Render(text) + m.dimSuffix(ev.Detail))
	case "warn":
		if ev.Transient {
			m.addLive(m.g.Warn + " " + text)
			return
		}
		m.warnings++
		m.persist(m.st.Warn.Render(m.g.Warn) + " " + m.st.Text.Render(text) + m.dimSuffix(ev.Detail))
	case "error":
		m.errors = append(m.errors, text)
		p := m.ensurePhase()
		p.errorTexts = append(p.errorTexts, text)
		m.persist(m.st.Fail.Render(m.g.Fail) + " " + m.st.Text.Render(text) + m.dimSuffix(ev.Detail))
	default: // step, info, item: transient narration
		if ev.Level == "info" {
			m.lastInfo = text
		}
		line := text
		if ev.Detail != "" {
			line += " (" + ev.Detail + ")"
		}
		m.addLive(line)
	}
}

func (m *model) handleProgress(ev Event) {
	var t *transfer
	for _, x := range m.transfers {
		if x.id == ev.ID {
			t = x
		}
	}
	switch ev.State {
	case "done", "fail":
		kept := m.transfers[:0]
		for _, x := range m.transfers {
			if x.id != ev.ID {
				kept = append(kept, x)
			}
		}
		m.transfers = kept
		return
	}
	if t == nil {
		t = &transfer{id: ev.ID}
		m.transfers = append(m.transfers, t)
	}
	t.label, t.done, t.total = ev.Label, ev.Done, ev.Total
	if ev.State == "run" && t.state != "run" {
		t.started = m.now()
	}
	t.state = ev.State
}

func (m *model) handleCommand(ev Event) {
	switch ev.State {
	case "start":
		m.commands = append(m.commands, &runningCommand{id: ev.ID, text: ev.Text, started: m.now()})
	case "output":
		m.addLive(ev.Text)
	case "end":
		kept := m.commands[:0]
		var ended *runningCommand
		for _, c := range m.commands {
			if c.id == ev.ID {
				ended = c
				continue
			}
			kept = append(kept, c)
		}
		m.commands = kept
		if !ev.OK && ended != nil {
			m.persist(m.st.Fail.Render(m.g.Fail) + " " + m.st.Text.Render("$ "+ended.text))
			for _, line := range ev.Tail {
				m.persist("  " + m.st.Faint.Render(m.g.Pipe+" "+line))
			}
		}
	}
}

func (m *model) finish(code int) tea.Cmd {
	m.finished = true
	m.exitCode = code
	m.prompt = nil
	for _, p := range m.phases {
		switch p.status {
		case phaseActive:
			status := phaseDone
			if code != 0 {
				status = phaseFailed
			}
			m.commitPhase(p, status)
		case phasePending:
			p.status = phaseSkipped // never reached; not printed
		}
	}
	m.transfers, m.commands, m.live, m.spinner = nil, nil, nil, ""
	m.prints = append(m.prints, m.renderOutcome())
	m.log.close(code)
	return tea.Quit
}

func (m *model) alreadyReported(p *phase, name string) bool {
	for _, e := range p.errorTexts {
		if name != "" && strings.HasPrefix(e, name) {
			return true
		}
	}
	return false
}

func (m *model) dimSuffix(detail string) string {
	if strings.TrimSpace(detail) == "" {
		return ""
	}
	return "  " + m.st.Faint.Render(detail)
}
