// mpv-config-ui renders the mpv-config deployer's progress.
//
//	mpv-config-ui [--] <deployer command...>   run and render a deployer command
//	mpv-config-ui --demo [--speed N]           replay a realistic install (no changes)
//	mpv-config-ui --bench                      stress the renderer, print timings
//	mpv-config-ui --version
//
// The deployer stays the single source of truth: this program only draws
// what the child reports (see protocol.go) and answers its prompts.
package main

import (
	"fmt"
	"io"
	"os"
	"os/signal"
	"runtime"
	"strconv"
	"strings"
	"sync/atomic"
	"syscall"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

const version = "1.0.0"

// The renderer only repaints when the view changed and never faster than
// this; 30 fps is smooth for spinners/bars and cheap on the Windows console.
const framesPerSecond = 30

type renderStats struct {
	views  int
	writes atomic.Int64
	bytes  atomic.Int64
}

type countingWriter struct {
	w     io.Writer
	stats *renderStats
}

func (c countingWriter) Write(p []byte) (int, error) {
	c.stats.writes.Add(1)
	c.stats.bytes.Add(int64(len(p)))
	return c.w.Write(p)
}

// Read/Close/Fd make the wrapper a term.File, so Bubble Tea still detects the
// terminal (size, resize events) through it.
func (c countingWriter) Read([]byte) (int, error) { return 0, io.EOF }
func (c countingWriter) Close() error             { return nil }

// Fd keeps terminal detection working through the wrapper.
func (c countingWriter) Fd() uintptr {
	if f, ok := c.w.(*os.File); ok {
		return f.Fd()
	}
	return ^uintptr(0)
}

var knownActions = []string{"install", "update", "verify", "rollback", "status", "sync-deps", "uninstall"}

func commandLabel(argv []string) string {
	for _, a := range argv {
		name := strings.TrimPrefix(strings.SplitN(a, "=", 2)[0], "--")
		for _, known := range knownActions {
			if name == known {
				return known
			}
		}
	}
	return ""
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: mpv-config-ui [--] <command...> | --demo [--speed N] | --bench | --version")
}

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	demo, bench := false, false
	speed := 1.0
	var child []string
	for i := 0; i < len(args); i++ {
		switch a := args[i]; a {
		case "--version":
			fmt.Println("mpv-config-ui", version, runtime.GOOS+"/"+runtime.GOARCH)
			return 0
		case "--demo":
			demo = true
		case "--bench":
			bench = true
		case "--speed":
			if i+1 < len(args) {
				if v, err := strconv.ParseFloat(args[i+1], 64); err == nil {
					speed = v
				}
				i++
			}
		case "--":
			child = args[i+1:]
			i = len(args)
		default:
			child = args[i:]
			i = len(args)
		}
	}
	if !demo && !bench && len(child) == 0 {
		usage()
		return 2
	}

	var src Source
	command := commandLabel(child)
	switch {
	case bench:
		src, command = newDemoSource(true, 1), "bench"
	case demo:
		src, command = newDemoSource(false, speed), "install"
	default:
		src = newChildSource(child)
	}

	logFile := openRunLog(command)
	if demo || bench {
		logFile = &runLog{}
	}
	m := newModel(src, command, runtime.GOOS+"/"+runtime.GOARCH, currentGlyphs(), logFile)
	stats := &renderStats{}
	if bench {
		m.stats = stats
		src.(*demoSource).stats = stats
	}

	var output io.Writer = os.Stdout
	if bench {
		output = countingWriter{os.Stdout, stats}
	}
	p := tea.NewProgram(m,
		tea.WithOutput(output),
		tea.WithFPS(framesPerSecond),
		tea.WithoutSignalHandler(),
	)

	signals := make(chan os.Signal, 2)
	signal.Notify(signals, notifySignals()...)
	go func() {
		for s := range signals {
			p.Send(interruptMsg{fromSignal: s == os.Interrupt})
		}
	}()

	wallStart, cpuStart := time.Now(), cpuTime()
	started := make(chan struct{})
	go func() {
		<-started
		if err := src.Start(p.Send); err != nil {
			m.errors = append(m.errors, "could not start: "+err.Error())
			p.Send(childExitMsg{code: 127, err: err})
		}
	}()
	close(started)

	if _, err := p.Run(); err != nil {
		src.Kill()
		fmt.Fprintln(os.Stderr, "mpv-config-ui:", err)
		return 1
	}
	signal.Stop(signals)

	if bench {
		wall := time.Since(wallStart)
		cpu := cpuTime() - cpuStart
		fmt.Fprintf(os.Stderr, "bench %s/%s · total wall %s · cpu %s · %d views · %d writes · %.1f KB\n",
			runtime.GOOS, runtime.GOARCH, wall.Round(time.Millisecond), cpu.Round(time.Millisecond),
			stats.views, stats.writes.Load(), float64(stats.bytes.Load())/1024)
		if mk := src.(*demoSource).marks; len(mk) == 3 {
			burst, steady := mk[1], mk[2]
			fmt.Fprintf(os.Stderr, "  burst  (21k events): %s wall, %s cpu, %.1f KB to the terminal\n",
				(burst.wall - mk[0].wall).Round(time.Millisecond), (burst.cpu - mk[0].cpu).Round(time.Millisecond),
				float64(burst.bytes-mk[0].bytes)/1024)
			secs := (steady.wall - burst.wall).Seconds()
			fmt.Fprintf(os.Stderr, "  steady (animated download): %.1f%% of one core, %.1f KB/s to the terminal\n",
				100*(steady.cpu-burst.cpu).Seconds()/secs, float64(steady.bytes-burst.bytes)/1024/secs)
		}
	}
	return m.exitCode
}

func notifySignals() []os.Signal {
	if runtime.GOOS == "windows" {
		return []os.Signal{os.Interrupt}
	}
	return []os.Signal{os.Interrupt, syscall.SIGTERM, syscall.SIGHUP}
}
