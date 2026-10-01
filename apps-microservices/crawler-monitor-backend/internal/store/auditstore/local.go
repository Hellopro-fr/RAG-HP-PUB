package auditstore

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"
)

var fileRe = regexp.MustCompile(`^audit-(\d{4}-\d{2}-\d{2})\.log$`)

type Local struct {
	dir        string
	mu         sync.Mutex
	dirEnsured bool
}

func New(dir string) *Local { return &Local{dir: dir} }

func (l *Local) ensureDir() error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.dirEnsured {
		return nil
	}
	if err := os.MkdirAll(l.dir, 0o755); err != nil {
		return err
	}
	l.dirEnsured = true
	return nil
}

func (l *Local) Append(ctx context.Context, entry map[string]any) error {
	if err := l.ensureDir(); err != nil {
		return err
	}
	if entry["ts"] == nil {
		entry["ts"] = time.Now().UTC().Format(time.RFC3339Nano)
	}
	b, err := json.Marshal(entry)
	if err != nil {
		return err
	}
	day := time.Now().UTC().Format("2006-01-02")
	path := filepath.Join(l.dir, "audit-"+day+".log")
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = f.Write(append(b, '\n'))
	return err
}

type Filter struct {
	From   time.Time
	To     time.Time
	Action string
	User   string
	Target string
	Limit  int
	Offset int
}

type Page struct {
	Items  []map[string]any `json:"items"`
	Total  int              `json:"total"`
	Limit  int              `json:"limit"`
	Offset int              `json:"offset"`
}

func (l *Local) Read(ctx context.Context, f Filter) (*Page, error) {
	if f.From.IsZero() {
		f.From = time.Now().Add(-24 * time.Hour)
	}
	if f.To.IsZero() {
		f.To = time.Now()
	}
	if f.To.Before(f.From) {
		return nil, errors.New("`to` must be >= `from`")
	}
	const maxWindow = 30 * 24 * time.Hour
	if f.To.Sub(f.From) > maxWindow {
		return nil, errors.New("Window too wide (max 30 days)")
	}
	if f.Limit <= 0 {
		f.Limit = 100
	}
	if f.Limit > 500 {
		f.Limit = 500
	}
	if f.Offset < 0 {
		f.Offset = 0
	}

	day := time.Date(f.From.UTC().Year(), f.From.UTC().Month(), f.From.UTC().Day(), 0, 0, 0, 0, time.UTC)
	endDay := time.Date(f.To.UTC().Year(), f.To.UTC().Month(), f.To.UTC().Day(), 0, 0, 0, 0, time.UTC)

	var matches []map[string]any
	for !day.After(endDay) {
		path := filepath.Join(l.dir, "audit-"+day.Format("2006-01-02")+".log")
		fh, err := os.Open(path)
		if err != nil {
			if errors.Is(err, fs.ErrNotExist) {
				day = day.Add(24 * time.Hour)
				continue
			}
			return nil, err
		}
		sc := bufio.NewScanner(fh)
		sc.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)
		for sc.Scan() {
			line := strings.TrimSpace(sc.Text())
			if line == "" {
				continue
			}
			var e map[string]any
			if err := json.Unmarshal([]byte(line), &e); err != nil {
				continue
			}
			ts, _ := e["ts"].(string)
			t, err := time.Parse(time.RFC3339Nano, ts)
			if err != nil {
				continue
			}
			if t.Before(f.From) || t.After(f.To) {
				continue
			}
			if f.Action != "" && e["action"] != f.Action {
				continue
			}
			if f.User != "" && e["user"] != f.User {
				continue
			}
			if f.Target != "" && e["target"] != f.Target {
				continue
			}
			matches = append(matches, e)
		}
		fh.Close()
		day = day.Add(24 * time.Hour)
	}

	sort.Slice(matches, func(i, j int) bool {
		ti, _ := time.Parse(time.RFC3339Nano, matches[i]["ts"].(string))
		tj, _ := time.Parse(time.RFC3339Nano, matches[j]["ts"].(string))
		return ti.After(tj)
	})

	total := len(matches)
	from := f.Offset
	if from > total {
		from = total
	}
	to := from + f.Limit
	if to > total {
		to = total
	}
	return &Page{Items: matches[from:to], Total: total, Limit: f.Limit, Offset: f.Offset}, nil
}

func (l *Local) RotateOld(ctx context.Context, retentionDays int) (int, error) {
	entries, err := os.ReadDir(l.dir)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return 0, nil
		}
		return 0, err
	}
	cutoff := time.Now().Add(-time.Duration(retentionDays) * 24 * time.Hour)
	deleted := 0
	for _, e := range entries {
		m := fileRe.FindStringSubmatch(e.Name())
		if m == nil {
			continue
		}
		t, err := time.Parse("2006-01-02", m[1])
		if err != nil {
			continue
		}
		if t.Before(cutoff) {
			if err := os.Remove(filepath.Join(l.dir, e.Name())); err == nil {
				deleted++
			}
		}
	}
	return deleted, nil
}

func (l *Local) Path(day time.Time) string {
	return filepath.Join(l.dir, fmt.Sprintf("audit-%s.log", day.UTC().Format("2006-01-02")))
}
