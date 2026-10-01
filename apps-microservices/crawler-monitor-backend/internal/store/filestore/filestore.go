package filestore

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
)

type Storage struct{ base string }

func New(base string) *Storage  { return &Storage{base: filepath.Clean(base)} }
func (s *Storage) Base() string { return s.base }

func (s *Storage) Read(ctx context.Context, parts ...string) ([]byte, error) {
	p, err := SafeJoin(s.base, parts...)
	if err != nil {
		return nil, err
	}
	return os.ReadFile(p)
}

func (s *Storage) Write(ctx context.Context, data []byte, parts ...string) error {
	p, err := SafeJoin(s.base, parts...)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		return err
	}
	return os.WriteFile(p, data, 0o644)
}

func (s *Storage) Delete(ctx context.Context, parts ...string) error {
	p, err := SafeJoin(s.base, parts...)
	if err != nil {
		return err
	}
	if err := os.Remove(p); err != nil && !errors.Is(err, fs.ErrNotExist) {
		return err
	}
	return nil
}

func (s *Storage) ListDir(ctx context.Context, parts ...string) ([]os.DirEntry, error) {
	p, err := SafeJoin(s.base, parts...)
	if err != nil {
		return nil, err
	}
	return os.ReadDir(p)
}
