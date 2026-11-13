//go:build windows

package main

import (
	"os"
	"os/exec"
	"syscall"

	"golang.org/x/sys/windows"
)

// A new process group: console Ctrl+C no longer hits the child behind our
// back, so cancellation is one controlled path on Windows as on Linux.
func configureChild(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: windows.CREATE_NEW_PROCESS_GROUP}
}

// CTRL_BREAK is the only console event deliverable to another process
// group; the deployer maps SIGBREAK to KeyboardInterrupt in protocol mode.
func interruptChild(p *os.Process) {
	_ = windows.GenerateConsoleCtrlEvent(windows.CTRL_BREAK_EVENT, uint32(p.Pid))
}

const signalReachesChild = false
