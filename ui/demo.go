package main

import (
	"encoding/json"
	"fmt"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

// demoSource replays a realistic install so the design can be previewed (and
// recorded) without touching the machine. In benchmark mode it replays a much
// larger stream with no pauses, through the same JSON parser the real child
// output goes through, to measure the renderer's cost on this terminal.
type benchMark struct {
	wall, cpu time.Duration
	bytes     int64
}

type demoSource struct {
	bench   bool
	stats   *renderStats
	marks   []benchMark
	speed   float64
	replies chan any
	stop    chan struct{}
}

func newDemoSource(bench bool, speed float64) *demoSource {
	if speed <= 0 {
		speed = 1
	}
	return &demoSource{bench: bench, speed: speed, replies: make(chan any, 1), stop: make(chan struct{})}
}

func (d *demoSource) Reply(id int, value any) {
	select {
	case d.replies <- value:
	default:
	}
}

func (d *demoSource) Interrupt() {
	select {
	case <-d.stop:
	default:
		close(d.stop)
	}
}

func (d *demoSource) Kill() { d.Interrupt() }

func (d *demoSource) Start(send func(tea.Msg)) error {
	go func() {
		// Same batching path as a real child, so --bench measures it.
		batch := newBatcher(send)
		code := d.run(batch.push)
		batch.close()
		send(childExitMsg{code: code})
	}()
	return nil
}

type demoCtx struct {
	d    *demoSource
	send func(tea.Msg)
	id   int
}

var errDemoStopped = fmt.Errorf("stopped")

func (c *demoCtx) wait(ms int) error {
	if c.d.bench {
		select {
		case <-c.d.stop:
			return errDemoStopped
		default:
			return nil
		}
	}
	select {
	case <-c.d.stop:
		return errDemoStopped
	case <-time.After(time.Duration(float64(ms)/c.d.speed) * time.Millisecond):
		return nil
	}
}

// emit goes through JSON + parseLine exactly like real child output.
func (c *demoCtx) emit(fields map[string]any) {
	data, _ := json.Marshal(fields)
	if ev, ok := parseLine(recordSeparator + string(data)); ok {
		c.send(eventMsg{ev})
	}
}

func (c *demoCtx) ask(fields map[string]any) (any, error) {
	c.id++
	fields["id"] = c.id
	c.emit(fields)
	if c.d.bench {
		return fields["default"], nil
	}
	select {
	case v := <-c.d.replies:
		return v, nil
	case <-c.d.stop:
		return nil, errDemoStopped
	}
}

func (c *demoCtx) log(level, text string, detail ...string) {
	ev := map[string]any{"t": "log", "level": level, "text": text}
	if len(detail) > 0 {
		ev["detail"] = detail[0]
	}
	c.emit(ev)
}

func (c *demoCtx) download(label string, total int64, steps, ms int) error {
	c.id++
	id := c.id
	c.emit(map[string]any{"t": "progress", "id": id, "label": label, "state": "connect"})
	if err := c.wait(ms * 3); err != nil {
		return err
	}
	for i := 1; i <= steps; i++ {
		done := total * int64(i) / int64(steps)
		c.emit(map[string]any{"t": "progress", "id": id, "label": label, "state": "run", "done": done, "total": total})
		if err := c.wait(ms); err != nil {
			return err
		}
	}
	c.emit(map[string]any{"t": "progress", "id": id, "label": label, "state": "done", "done": total, "total": total})
	return nil
}

func (c *demoCtx) command(text string, ms int) error {
	c.id++
	id := c.id
	c.emit(map[string]any{"t": "command", "state": "start", "id": id, "text": text})
	if err := c.wait(ms); err != nil {
		return err
	}
	c.emit(map[string]any{"t": "command", "state": "end", "id": id, "ok": true, "secs": float64(ms) / 1000})
	return nil
}

func (d *demoSource) run(send func(tea.Msg)) int {
	c := &demoCtx{d: d, send: send}
	if d.bench {
		d.benchScript(c)
		return 0
	}
	if err := d.script(c); err != nil {
		c.log("error", "Interrupted by user.")
		return 130
	}
	return 0
}

func (d *demoSource) script(c *demoCtx) error {
	c.emit(map[string]any{"t": "hello", "v": protocolVersion, "command": "install"})
	c.emit(map[string]any{"t": "outline", "steps": []map[string]string{
		{"key": "detect", "title": "Detect environment"},
		{"key": "plan", "title": "Review plan"},
		{"key": "anime", "title": "Anime4K mode"},
		{"key": "fetch", "title": "Download scripts & shaders"},
		{"key": "deps", "title": "Install dependencies"},
		{"key": "deploy", "title": "Deploy configuration"},
		{"key": "verify", "title": "Verify"},
	}})
	steps := []func() error{
		func() error {
			c.emit(map[string]any{"t": "phase", "key": "detect", "title": "Detecting Environment"})
			c.emit(map[string]any{"t": "spinner", "state": "start", "text": "Detecting environment..."})
			if err := c.wait(900); err != nil {
				return err
			}
			c.emit(map[string]any{"t": "spinner", "state": "stop"})
			c.emit(map[string]any{"t": "table", "title": "Detection Results", "columns": []string{"Property", "Value"},
				"rows": [][]string{{"OS", "linux (CachyOS)"}, {"Display", "wayland"}, {"GPU", "nvidia (nvdec)"},
					{"Package manager", "pacman + paru"}, {"mpv config dir", "~/.config/mpv"}}})
			return c.wait(300)
		},
		func() error {
			c.emit(map[string]any{"t": "phase", "key": "plan", "title": "Installation Plan"})
			c.emit(map[string]any{"t": "plan", "title": "Installation Plan", "groups": []map[string]any{
				{"label": "Packages", "entries": []map[string]string{
					{"action": "install", "target": "mpv"}, {"action": "refresh", "target": "yt-dlp"},
					{"action": "install", "target": "ffsubsync"}, {"action": "install", "target": "alass"},
					{"action": "skip", "target": "ffmpeg"}, {"action": "skip", "target": "python"}, {"action": "skip", "target": "uv"}}},
				{"label": "Scripts", "entries": []map[string]string{
					{"action": "fetch", "target": "uosc"}, {"action": "fetch", "target": "thumbfast"},
					{"action": "fetch", "target": "SmartSkip"}, {"action": "fetch", "target": "sponsorblock"},
					{"action": "fetch", "target": "autosubsync"}, {"action": "fetch", "target": "memo"},
					{"action": "fetch", "target": "evafast"}, {"action": "fetch", "target": "Anime4K"}}},
				{"label": "Backup", "entries": []map[string]string{{"action": "backup", "target": "~/.config/mpv"}}},
				{"label": "Config", "entries": []map[string]string{
					{"action": "deploy", "target": "~/.config/mpv/scripts/"}, {"action": "deploy", "target": "~/.config/mpv/shaders/"},
					{"action": "deploy", "target": "~/.config/mpv/mpv.conf"}, {"action": "deploy", "target": "~/.config/mpv/input.conf"},
					{"action": "deploy", "target": "~/.config/mpv/script-opts/"}}},
			}})
			v, err := c.ask(map[string]any{"t": "prompt", "kind": "confirm", "text": "Proceed with installation?", "default": true})
			if err != nil {
				return err
			}
			if v == false {
				return errDemoStopped
			}
			return nil
		},
		func() error {
			c.emit(map[string]any{"t": "phase", "key": "anime", "title": "Anime4K shader mode"})
			v, err := c.ask(map[string]any{"t": "prompt", "kind": "menu", "text": "Anime4K mode", "default": 0,
				"items": []map[string]string{
					{"value": "A+A", "label": "balanced restore + upscale (recommended)"},
					{"value": "A", "label": "restore, lighter"},
					{"value": "B", "label": "soft sources"},
					{"value": "C", "label": "already sharp sources"},
					{"value": "off", "label": "no shaders"},
				}})
			if err != nil {
				return err
			}
			c.ensureNote(fmt.Sprint(v))
			return nil
		},
		func() error {
			c.emit(map[string]any{"t": "phase", "key": "fetch", "title": "Fetching Scripts & Shaders"})
			for _, s := range []struct {
				name string
				size int64
			}{{"uosc.zip", 1_480_000}, {"thumbfast.lua", 38_000}, {"SmartSkip.lua", 61_000},
				{"sponsorblock.lua", 22_000}, {"autosubsync", 34_000}, {"memo.lua", 29_000}, {"Anime4K_v4.0.zip", 5_600_000}} {
				if err := c.download(s.name, s.size, 14, 70); err != nil {
					return err
				}
				c.log("ok", s.name+": downloaded")
			}
			c.emit(map[string]any{"t": "summary", "succeeded": 10})
			return nil
		},
		func() error {
			c.emit(map[string]any{"t": "phase", "key": "deps", "title": "Installing System Dependencies"})
			if err := c.command("sudo pacman -S --noconfirm --needed mpv", 1600); err != nil {
				return err
			}
			c.log("ok", "mpv 0.41.0", "cachyos-extra-v3")
			if err := c.download("yt-dlp", 3_100_000, 18, 60); err != nil {
				return err
			}
			c.log("ok", "yt-dlp 2026.11.02")
			if err := c.command("uv tool install ffsubsync", 1400); err != nil {
				return err
			}
			c.log("ok", "ffsubsync")
			c.log("warn", "alass has no Linux build for this CPU", "subtitle sync falls back to ffsubsync")
			c.emit(map[string]any{"t": "summary", "succeeded": 6, "skipped": 1})
			return nil
		},
		func() error {
			c.emit(map[string]any{"t": "phase", "key": "deploy", "title": "Deploying Configuration"})
			for _, s := range []string{"Backing up ~/.config/mpv", "Preparing scripts, shaders, fonts", "Writing mpv.conf for wayland + nvdec", "Applying uosc patches"} {
				c.log("step", s)
				if err := c.wait(450); err != nil {
					return err
				}
			}
			c.log("ok", "Backup created", "~/.config/mpv.backup.20261113_171204")
			c.emit(map[string]any{"t": "phase", "key": "verify", "title": "Verifying Deployment"})
			if err := c.wait(700); err != nil {
				return err
			}
			rows := [][]string{}
			for i := 0; i < 38; i++ {
				rows = append(rows, []string{"OK", fmt.Sprintf("check %d", i), ""})
			}
			rows = append(rows, []string{"SKIPPED", "mpv optimized build", "baseline build"})
			c.emit(map[string]any{"t": "table", "title": "Verification Results", "columns": []string{"Status", "Check", "Detail"}, "rows": rows})
			c.emit(map[string]any{"t": "panel", "title": "Success", "style": "green",
				"text": "Deployment complete.\nConfig: ~/.config/mpv\nTry: mpv --profile=anime <file>"})
			return nil
		},
	}
	for _, step := range steps {
		if err := step(); err != nil {
			return err
		}
	}
	return nil
}

func (c *demoCtx) ensureNote(text string) {
	c.log("info", "Anime4K mode: "+text)
}

func (d *demoSource) mark() {
	var written int64
	if d.stats != nil {
		written = d.stats.bytes.Load()
	}
	d.marks = append(d.marks, benchMark{wall: time.Duration(time.Now().UnixNano()), cpu: cpuTime(), bytes: written})
}

// benchScript measures two things: (1) burst throughput — ~21k events as fast
// as the producer can emit them; (2) steady-state cost — 6 s of a download
// reporting 10x/s with the spinner and timers animating, i.e. what a real
// install costs while you watch it.
func (d *demoSource) benchScript(c *demoCtx) {
	d.mark()
	c.emit(map[string]any{"t": "hello", "v": protocolVersion, "command": "bench"})
	for p := 0; p < 8; p++ {
		c.emit(map[string]any{"t": "phase", "key": fmt.Sprint(p), "title": fmt.Sprintf("Phase %d", p+1)})
		for i := 0; i < 250; i++ {
			c.log("step", fmt.Sprintf("narration line %d of phase %d", i, p))
		}
		for f := 0; f < 6; f++ {
			_ = c.download(fmt.Sprintf("asset-%d-%d.zip", p, f), 50_000_000, 400, 0)
			c.log("ok", fmt.Sprintf("asset-%d-%d.zip", p, f))
		}
		for k := 0; k < 25; k++ {
			_ = c.command(fmt.Sprintf("sudo pacman -S --noconfirm pkg-%d", k), 0)
		}
		c.emit(map[string]any{"t": "summary", "succeeded": 31})
	}
	time.Sleep(100 * time.Millisecond) // let the burst drain into the renderer
	d.mark()
	c.emit(map[string]any{"t": "phase", "key": "steady", "title": "Steady state"})
	const total = int64(60 * 100_000)
	for i := int64(1); i <= 60; i++ {
		c.emit(map[string]any{"t": "progress", "id": 99999, "label": "steady.zip", "state": "run",
			"done": i * 100_000, "total": total})
		time.Sleep(100 * time.Millisecond)
	}
	d.mark()
	c.emit(map[string]any{"t": "progress", "id": 99999, "label": "steady.zip", "state": "done"})
	c.emit(map[string]any{"t": "panel", "text": "Benchmark complete."})
}
