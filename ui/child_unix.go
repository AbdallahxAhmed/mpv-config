//go:build !windows

package main

import (
	"os"
	"os/exec"
	"syscall"
)

// The child stays in OUR process group and session: sudo's credential cache
// is keyed to the controlling terminal, and a background process group would
// be stopped (SIGTTOU) the moment sudo touches the terminal settings.
func configureChild(cmd *exec.Cmd) {}

// Raw mode disables the terminal's own Ctrl+C → SIGINT, so the key is
// forwarded explicitly. Python turns SIGINT into KeyboardInterrupt and the
// deployer's transaction code rolls back.
func interruptChild(p *os.Process) { _ = p.Signal(syscall.SIGINT) }

// Signals that also reached the child directly (same process group).
const signalReachesChild = true
