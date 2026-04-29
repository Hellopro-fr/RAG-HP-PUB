package tests

import (
	"context"
	"errors"
	"path/filepath"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
)

func TestPathTraversal_RejectMaliciousPaths(t *testing.T) {
	base := t.TempDir()
	s := filestore.New(base)
	cases := []struct {
		name string
		path []string
	}{
		{"parent dir", []string{"..", "secret"}},
		{"deep parent", []string{"..", "..", "..", "etc", "passwd"}},
		{"absolute", []string{"/etc/passwd"}},
		{"slash dotdot", []string{"sub/../..", "secret"}},
		{"trailing dotdot", []string{"sub/.."}},
		{"single dotdot middle", []string{"a", "..", "..", "b"}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			_, err := filestore.SafeJoin(base, c.path...)
			if err == nil || !errors.Is(err, filestore.ErrPathEscape) {
				t.Errorf("path %v: err = %v, want ErrPathEscape", c.path, err)
			}
			err = s.Delete(context.Background(), c.path...)
			if err == nil {
				t.Errorf("Delete should reject %v", c.path)
			}
		})
	}
}

func TestPathTraversal_AcceptValidPaths(t *testing.T) {
	base := t.TempDir()
	cases := [][]string{
		{"job1", "datasets", "0.json"},
		{"a", "b", "c.txt"},
	}
	for _, c := range cases {
		got, err := filestore.SafeJoin(base, c...)
		if err != nil {
			t.Errorf("SafeJoin(%v): %v", c, err)
		}
		want := filepath.Clean(filepath.Join(append([]string{base}, c...)...))
		if got != want {
			t.Errorf("got %s, want %s", got, want)
		}
	}
}

func TestFilestore_WriteReadDelete(t *testing.T) {
	base := t.TempDir()
	s := filestore.New(base)
	data := []byte("hello")
	if err := s.Write(context.Background(), data, "sub", "f.txt"); err != nil {
		t.Fatal(err)
	}
	got, err := s.Read(context.Background(), "sub", "f.txt")
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != "hello" {
		t.Errorf("got %q", got)
	}
	if err := s.Delete(context.Background(), "sub", "f.txt"); err != nil {
		t.Fatal(err)
	}
}
