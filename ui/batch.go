package main

import (
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

// batchMsg carries every event that arrived within one batching window.
type batchMsg []tea.Msg

const (
	batchWindow = 12 * time.Millisecond
	batchMax    = 2048
)

// batcher coalesces a burst of child output into one message so the model
// renders once per burst instead of once per line. Order is preserved;
// latency is at most one window (well under a frame).
type batcher struct {
	in   chan tea.Msg
	done chan struct{}
}

func newBatcher(send func(tea.Msg)) *batcher {
	b := &batcher{in: make(chan tea.Msg, 4096), done: make(chan struct{})}
	go func() {
		defer close(b.done)
		for first := range b.in {
			batch := batchMsg{first}
			timer := time.NewTimer(batchWindow)
		collect:
			for len(batch) < batchMax {
				select {
				case msg, ok := <-b.in:
					if !ok {
						break collect
					}
					batch = append(batch, msg)
				case <-timer.C:
					break collect
				}
			}
			timer.Stop()
			send(batch)
		}
	}()
	return b
}

func (b *batcher) push(msg tea.Msg) { b.in <- msg }

// close flushes what is pending and waits until it has been sent.
func (b *batcher) close() {
	close(b.in)
	<-b.done
}
