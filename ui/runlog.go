package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

// runLog keeps a plain-text record of everything the deployer said —
// including the transient lines the live view only flashes — so a failed run
// can be diagnosed after the screen has moved on.
type runLog struct {
	file  *os.File
	w     *bufio.Writer
	where string
}

const keepLogs = 10

func openRunLog(command string) *runLog {
	base, err := os.UserCacheDir()
	if err != nil {
		return &runLog{}
	}
	dir := filepath.Join(base, "mpv-config", "logs")
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return &runLog{}
	}
	if command == "" {
		command = "run"
	}
	name := fmt.Sprintf("%s-%s.log", command, time.Now().Format("20060102-150405"))
	f, err := os.OpenFile(filepath.Join(dir, name), os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		return &runLog{}
	}
	pruneLogs(dir)
	return &runLog{file: f, w: bufio.NewWriter(f), where: f.Name()}
}

func pruneLogs(dir string) {
	matches, _ := filepath.Glob(filepath.Join(dir, "*.log"))
	if len(matches) <= keepLogs {
		return
	}
	sort.Strings(matches) // timestamped names sort chronologically per command
	sort.SliceStable(matches, func(i, j int) bool {
		a, _ := os.Stat(matches[i])
		b, _ := os.Stat(matches[j])
		return a != nil && b != nil && a.ModTime().Before(b.ModTime())
	})
	for _, old := range matches[:len(matches)-keepLogs] {
		_ = os.Remove(old)
	}
}

func (l *runLog) write(kind, text string) {
	if l == nil || l.w == nil {
		return
	}
	fmt.Fprintf(l.w, "%s %-8s %s\n", time.Now().Format("15:04:05.000"), kind, text)
}

func (l *runLog) event(ev Event) {
	if l == nil || l.w == nil {
		return
	}
	switch ev.T {
	case "progress":
		if ev.State == "done" || ev.State == "fail" {
			l.write("progress", fmt.Sprintf("%s %s %d/%d", ev.Label, ev.State, ev.Done, ev.Total))
		}
	case "table":
		l.write("table", ev.Title)
		for _, row := range ev.Rows {
			l.write("", strings.Join(row, " | "))
		}
	case "plan":
		for _, g := range ev.Groups {
			for _, e := range g.Entries {
				l.write("plan", fmt.Sprintf("%s: %s %s — %s", g.Label, e.Action, e.Target, e.Detail))
			}
		}
	case "command":
		switch ev.State {
		case "start":
			l.write("command", "$ "+ev.Text)
		case "end":
			l.write("command", fmt.Sprintf("exit ok=%v after %.1fs", ev.OK, ev.Secs))
			for _, t := range ev.Tail {
				l.write("", "| "+t)
			}
		default:
			l.write("output", ev.Text)
		}
	default:
		text := ev.Text
		if text == "" {
			text = ev.Title
		}
		if ev.Detail != "" {
			text += " (" + ev.Detail + ")"
		}
		kind := ev.T
		if ev.Level != "" {
			kind = ev.Level
		}
		l.write(kind, text)
	}
}

func (l *runLog) line(text string, stderr bool) {
	kind := "stdout"
	if stderr {
		kind = "stderr"
	}
	l.write(kind, text)
}

func (l *runLog) close(code int) {
	if l == nil || l.w == nil {
		return
	}
	l.write("exit", fmt.Sprintf("code %d", code))
	_ = l.w.Flush()
	_ = l.file.Close()
	l.w = nil
}

// path is shown home-relative so the footer stays short.
func (l *runLog) path() string {
	if l == nil || l.where == "" {
		return ""
	}
	if home, err := os.UserHomeDir(); err == nil && strings.HasPrefix(l.where, home) {
		return "~" + l.where[len(home):]
	}
	return l.where
}
