package main

// Wire protocol between the Python deployer (producer) and this renderer.
//
// The deployer runs as our child with MPV_CONFIG_UI_PROTOCOL=1. Every event is
// one line on its stdout: the ASCII record separator (0x1E) followed by a JSON
// object. Lines WITHOUT the separator are stray output (a library print, a
// warning) and are shown as plain log lines, so a stray print can never
// corrupt the stream. Prompt answers travel back on the child's stdin as one
// JSON object per line: {"id": <prompt id>, "value": <answer>}.
//
// The full schema is documented in ui/PROTOCOL.md.

import (
	"encoding/json"
	"strings"
)

const (
	protocolVersion = 1
	recordSeparator = "\x1e"
)

type PlanEntry struct {
	Action string `json:"action"`
	Target string `json:"target"`
	Detail string `json:"detail"`
}

type PlanGroup struct {
	Label   string      `json:"label"`
	Entries []PlanEntry `json:"entries"`
}

type MenuItem struct {
	Value string `json:"value"`
	Label string `json:"label"`
}

type OutlineStep struct {
	Key   string `json:"key"`
	Title string `json:"title"`
}

type FailedResult struct {
	Name   string `json:"name"`
	Detail string `json:"detail"`
}

// Event is the union of every message type; T selects which fields matter.
type Event struct {
	T string `json:"t"`

	// hello
	V       int    `json:"v"`
	Command string `json:"command"`

	// outline / phase
	Steps []OutlineStep `json:"steps"`
	Key   string        `json:"key"`
	Title string        `json:"title"`

	// log / spinner / panel / prompt / sudo / command
	Level  string `json:"level"`
	Text   string `json:"text"`
	Detail string `json:"detail"`
	Style  string `json:"style"`
	Reason string `json:"reason"`
	// Transient log lines (retry notices) are shown live but not kept.
	Transient bool `json:"transient"`

	// table / plan / summary
	Columns   []string       `json:"columns"`
	Rows      [][]string     `json:"rows"`
	Groups    []PlanGroup    `json:"groups"`
	Succeeded int            `json:"succeeded"`
	Skipped   int            `json:"skipped"`
	Failed    []FailedResult `json:"failed"`

	// progress / command / prompt
	ID      int             `json:"id"`
	Label   string          `json:"label"`
	State   string          `json:"state"`
	Done    int64           `json:"done"`
	Total   int64           `json:"total"`
	OK      bool            `json:"ok"`
	Secs    float64         `json:"secs"`
	Tail    []string        `json:"tail"`
	Kind    string          `json:"kind"`
	Items   []MenuItem      `json:"items"`
	Default json.RawMessage `json:"default"`
}

// parseLine classifies one stdout line from the child: an event (ok=true) or
// plain text that should be displayed as-is.
func parseLine(line string) (Event, bool) {
	line = strings.TrimRight(line, "\r\n")
	idx := strings.Index(line, recordSeparator)
	if idx < 0 {
		return Event{}, false
	}
	var ev Event
	if err := json.Unmarshal([]byte(line[idx+len(recordSeparator):]), &ev); err != nil || ev.T == "" {
		return Event{}, false
	}
	return ev, true
}

// encodeReply builds the line written to the child's stdin for a prompt.
func encodeReply(id int, value any) []byte {
	data, _ := json.Marshal(struct {
		ID    int `json:"id"`
		Value any `json:"value"`
	}{id, value})
	return append(data, '\n')
}
