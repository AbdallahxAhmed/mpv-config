package main

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/x/ansi"
)

type fakeSource struct {
	replies     []any
	interrupted int
	killed      int
}

func (f *fakeSource) Start(func(tea.Msg)) error { return nil }
func (f *fakeSource) Reply(id int, v any)       { f.replies = append(f.replies, v) }
func (f *fakeSource) Interrupt()                { f.interrupted++ }
func (f *fakeSource) Kill()                     { f.killed++ }

func newTestModel() (*model, *fakeSource) {
	src := &fakeSource{}
	m := newModel(src, "install", "linux/amd64", richGlyphs, &runLog{})
	clock := time.Date(2026, 11, 13, 12, 0, 0, 0, time.UTC)
	m.now = func() time.Time { clock = clock.Add(100 * time.Millisecond); return clock }
	m.width = 90
	return m, src
}

func send(m *model, raw string) tea.Cmd {
	ev, ok := parseLine(recordSeparator + raw)
	if !ok {
		panic("bad event: " + raw)
	}
	_, cmd := m.Update(eventMsg{ev})
	return cmd
}

func plain(s string) string { return ansi.Strip(s) }

func TestParseLineSeparatesEventsFromStrayOutput(t *testing.T) {
	if _, ok := parseLine("plain print from a library"); ok {
		t.Fatal("stray output must not parse as an event")
	}
	if _, ok := parseLine(recordSeparator + "{not json"); ok {
		t.Fatal("broken JSON must not parse")
	}
	ev, ok := parseLine(recordSeparator + `{"t":"log","level":"ok","text":"done"}` + "\r\n")
	if !ok || ev.T != "log" || ev.Text != "done" {
		t.Fatalf("unexpected parse: %+v %v", ev, ok)
	}
}

func TestEncodeReplyIsOneJSONLine(t *testing.T) {
	line := encodeReply(7, "A+A")
	if !strings.HasSuffix(string(line), "\n") || strings.Count(string(line), "\n") != 1 {
		t.Fatalf("reply must be exactly one line: %q", line)
	}
	var got struct {
		ID    int    `json:"id"`
		Value string `json:"value"`
	}
	if err := json.Unmarshal(line, &got); err != nil || got.ID != 7 || got.Value != "A+A" {
		t.Fatalf("bad reply %q: %v", line, err)
	}
}

func TestOutlinePhasesCompleteInOrderAndSkippedStepsAreMarked(t *testing.T) {
	m, _ := newTestModel()
	send(m, `{"t":"outline","steps":[{"key":"a","title":"A"},{"key":"b","title":"B"},{"key":"c","title":"C"}]}`)
	send(m, `{"t":"phase","key":"a","title":"Alpha header"}`)
	if m.phases[0].status != phaseActive || m.phases[0].title != "A" {
		t.Fatalf("outline title must win: %+v", m.phases[0])
	}
	send(m, `{"t":"phase","key":"c","title":"Gamma"}`)
	if m.phases[0].status != phaseDone || m.phases[1].status != phaseSkipped || m.phases[2].status != phaseActive {
		t.Fatalf("statuses: %v %v %v", m.phases[0].status, m.phases[1].status, m.phases[2].status)
	}
	send(m, `{"t":"phase","key":"x","title":"Unplanned"}`)
	if m.phases[3].title != "Unplanned" || m.phases[3].status != phaseActive {
		t.Fatalf("unknown phases are appended after the active one: %+v", m.phases[3])
	}
}

func TestConfirmPromptRepliesThroughTheSource(t *testing.T) {
	m, src := newTestModel()
	send(m, `{"t":"phase","key":"plan","title":"Plan"}`)
	send(m, `{"t":"prompt","id":3,"kind":"confirm","text":"Proceed?","default":true}`)
	if m.prompt == nil || m.prompt.cursor != 0 {
		t.Fatal("confirm prompt should default to Yes")
	}
	m.Update(tea.KeyMsg{Type: tea.KeyRight})
	m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	if len(src.replies) != 1 || src.replies[0] != false || m.prompt != nil {
		t.Fatalf("expected a single 'false' reply, got %v", src.replies)
	}
}

func TestMenuPromptDigitsEscAndPhaseNote(t *testing.T) {
	m, src := newTestModel()
	send(m, `{"t":"phase","key":"anime","title":"Anime4K mode"}`)
	menu := `{"t":"prompt","id":4,"kind":"menu","text":"Mode","default":1,"items":[{"value":"A+A"},{"value":"A"},{"value":"off"}]}`
	send(m, menu)
	m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("3")})
	if src.replies[0] != "off" || m.activePhase().note != "off" {
		t.Fatalf("digit pick: %v note %q", src.replies, m.activePhase().note)
	}
	send(m, menu)
	m.Update(tea.KeyMsg{Type: tea.KeyEsc})
	if src.replies[1] != "A" {
		t.Fatalf("esc keeps the default row, got %v", src.replies[1])
	}
}

func TestCtrlCInterruptsOnceThenKills(t *testing.T) {
	m, src := newTestModel()
	m.Update(tea.KeyMsg{Type: tea.KeyCtrlC})
	m.Update(tea.KeyMsg{Type: tea.KeyCtrlC})
	if src.interrupted != 1 || src.killed != 1 {
		t.Fatalf("interrupted=%d killed=%d", src.interrupted, src.killed)
	}
}

func TestSignalAlreadyDeliveredToChildIsNotForwardedTwice(t *testing.T) {
	m, src := newTestModel()
	m.Update(interruptMsg{fromSignal: true})
	want := 1
	if signalReachesChild {
		want = 0 // a second SIGINT could land inside the rollback itself
	}
	if src.interrupted != want {
		t.Fatalf("interrupted=%d want %d", src.interrupted, want)
	}
}

func TestVerificationTableCollapsesToACountAndFailures(t *testing.T) {
	m, _ := newTestModel()
	send(m, `{"t":"phase","key":"verify","title":"Verify"}`)
	send(m, `{"t":"table","columns":["Status","Check","Detail"],"rows":[["OK","a",""],["OK","b",""],["FAILED","mpv launch test","exit 1"],["SKIPPED","c",""]]}`)
	p := m.activePhase()
	if p.note != "2/3 checks passed · 1 skipped" {
		t.Fatalf("note %q", p.note)
	}
	if len(p.lines) != 1 || !strings.Contains(plain(p.lines[0]), "mpv launch test") {
		t.Fatalf("only the failing row is listed: %q", p.lines)
	}
}

func TestPlanGroupsCountUnchangedAndCollapseOverflow(t *testing.T) {
	m, _ := newTestModel()
	m.width = 60
	lines := m.renderPlan(Event{Groups: []PlanGroup{{Label: "Packages", Entries: []PlanEntry{
		{Action: "install", Target: "mpv"}, {Action: "skip", Target: "ffmpeg"},
		{Action: "install", Target: "a-very-long-package-name"}, {Action: "install", Target: "another-long-one"},
		{Action: "install", Target: "and-one-more-package"},
	}}}})
	got := plain(lines[0])
	if !strings.Contains(got, "1 unchanged") || !strings.Contains(got, "more") {
		t.Fatalf("plan line %q", got)
	}
}

func TestViewNeverExceedsTheTerminalWidth(t *testing.T) {
	for _, width := range []int{40, 60, 80, 120} {
		m, _ := newTestModel()
		m.width = width
		send(m, `{"t":"outline","steps":[{"key":"f","title":"Download scripts and shaders with a long title"}]}`)
		send(m, `{"t":"phase","key":"f","title":"x"}`)
		send(m, `{"t":"progress","id":1,"label":"Anime4K_v4.0.1_with_a_really_long_name.zip","state":"run","done":1048576,"total":5242880}`)
		send(m, `{"t":"command","state":"start","id":2,"text":"sudo pacman -S --noconfirm --needed mpv ffmpeg yt-dlp python-pip uv"}`)
		send(m, `{"t":"log","level":"warn","text":"a warning that is far too long to fit on a narrow terminal line at all"}`)
		for _, line := range strings.Split(m.View(), "\n") {
			if w := ansi.StringWidth(line); w >= width {
				t.Fatalf("width %d: line is %d columns: %q", width, w, plain(line))
			}
		}
	}
}

func TestFailureOutcomeShowsErrorsAndStderrTail(t *testing.T) {
	m, _ := newTestModel()
	send(m, `{"t":"phase","key":"deps","title":"Dependencies"}`)
	send(m, `{"t":"log","level":"error","text":"Fatal error: Dependency installation failed"}`)
	m.Update(lineMsg{text: "Traceback (most recent call last):", stderr: true})
	m.Update(childExitMsg{code: 1})
	out := plain(m.renderOutcome())
	for _, want := range []string{"Install failed", "Dependency installation failed", "Traceback", "Exit code 1"} {
		if !strings.Contains(out, want) {
			t.Fatalf("outcome lacks %q:\n%s", want, out)
		}
	}
	if m.phases[0].status != phaseFailed {
		t.Fatal("the active phase must be marked failed")
	}
}

func TestGlyphTierFollowsTerminalCapability(t *testing.T) {
	env := func(kv map[string]string) func(string) string {
		return func(k string) string { return kv[k] }
	}
	cases := []struct {
		name string
		env  map[string]string
		goos string
		want string
	}{
		{"windows terminal", map[string]string{"WT_SESSION": "x"}, "windows", "✓"},
		{"legacy conhost", map[string]string{}, "windows", "√"},
		{"vscode on windows", map[string]string{"TERM_PROGRAM": "vscode"}, "windows", "✓"},
		{"linux emulator", map[string]string{"TERM": "xterm-256color"}, "linux", "✓"},
		{"linux virtual console", map[string]string{"TERM": "linux"}, "linux", "√"},
		{"override", map[string]string{"TERM": "linux", "MPV_CONFIG_UI_GLYPHS": "rich"}, "linux", "✓"},
	}
	for _, c := range cases {
		if got := detectGlyphs(env(c.env), c.goos).OK; got != c.want {
			t.Errorf("%s: got %q want %q", c.name, got, c.want)
		}
	}
}

func TestCommandLabel(t *testing.T) {
	if got := commandLabel([]string{"python", "-m", "deploy.deployer", "--install", "--yes"}); got != "install" {
		t.Fatalf("got %q", got)
	}
	if got := commandLabel([]string{"py", "--rollback=/x"}); got != "rollback" {
		t.Fatalf("got %q", got)
	}
}
