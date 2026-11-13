package main

import (
	"bufio"
	"io"
	"os"
	"os/exec"
	"sync"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/x/term"
)

// Source feeds events into the model: the real deployer child process, or
// the built-in demo/benchmark script.
type Source interface {
	Start(send func(tea.Msg)) error
	Reply(id int, value any)
	// Interrupt asks for a graceful stop (KeyboardInterrupt in Python, so
	// the transaction code can roll back). Kill is the last resort.
	Interrupt()
	Kill()
}

type eventMsg struct{ ev Event }

type lineMsg struct {
	text   string
	stderr bool
}

type childExitMsg struct {
	code int
	err  error
}

type childSource struct {
	argv  []string
	cmd   *exec.Cmd
	stdin io.WriteCloser
	mu    sync.Mutex
}

func newChildSource(argv []string) *childSource { return &childSource{argv: argv} }

func (c *childSource) Start(send func(tea.Msg)) error {
	cmd := exec.Command(c.argv[0], c.argv[1:]...)
	env := append(os.Environ(),
		"MPV_CONFIG_UI_PROTOCOL=1",
		"PYTHONUNBUFFERED=1",
		"PYTHONIOENCODING=utf-8",
	)
	if term.IsTerminal(os.Stdin.Fd()) {
		env = append(env, "MPV_CONFIG_UI_INTERACTIVE=1")
	}
	cmd.Env = env
	configureChild(cmd)

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return err
	}
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return err
	}
	if err := cmd.Start(); err != nil {
		return err
	}
	c.cmd, c.stdin = cmd, stdin

	batch := newBatcher(send)
	var readers sync.WaitGroup
	pump := func(r io.Reader, isErr bool) {
		defer readers.Done()
		scanner := bufio.NewScanner(r)
		scanner.Buffer(make([]byte, 64*1024), 4*1024*1024)
		for scanner.Scan() {
			line := scanner.Text()
			if !isErr {
				if ev, ok := parseLine(line); ok {
					batch.push(eventMsg{ev})
					continue
				}
			}
			batch.push(lineMsg{text: line, stderr: isErr})
		}
	}
	readers.Add(2)
	go pump(stdout, false)
	go pump(stderr, true)
	go func() {
		readers.Wait()
		batch.close() // every event is delivered before the exit
		err := cmd.Wait()
		code := 0
		if cmd.ProcessState != nil {
			code = cmd.ProcessState.ExitCode()
		}
		if code < 0 { // killed by a signal
			code = 130
		}
		send(childExitMsg{code: code, err: err})
	}()
	return nil
}

func (c *childSource) Reply(id int, value any) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.stdin != nil {
		_, _ = c.stdin.Write(encodeReply(id, value))
	}
}

func (c *childSource) Interrupt() {
	if c.cmd != nil && c.cmd.Process != nil {
		interruptChild(c.cmd.Process)
	}
}

func (c *childSource) Kill() {
	if c.cmd != nil && c.cmd.Process != nil {
		_ = c.cmd.Process.Kill()
	}
}
