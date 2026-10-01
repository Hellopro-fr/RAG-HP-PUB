package filestore

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
)

var ErrPathEscape = errors.New("path escapes base directory")

func SafeJoin(base string, parts ...string) (string, error) {
	cleanBase := filepath.Clean(base)

	// Reject any absolute path in parts (e.g. "/etc/passwd")
	for _, p := range parts {
		if filepath.IsAbs(p) {
			return "", ErrPathEscape
		}
	}

	all := append([]string{cleanBase}, parts...)
	joined := filepath.Clean(filepath.Join(all...))
	prefix := cleanBase + string(os.PathSeparator)

	// joined must be strictly under cleanBase (not equal to it, and must start with prefix)
	if !strings.HasPrefix(joined, prefix) {
		return "", ErrPathEscape
	}
	return joined, nil
}
