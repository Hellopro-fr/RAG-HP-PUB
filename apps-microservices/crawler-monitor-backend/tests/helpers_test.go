package tests

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

type noopAudit struct{}

func (n *noopAudit) Append(_ context.Context, _ map[string]any) error { return nil }

type recordingAudit struct {
	Entries []map[string]any
}

func (r *recordingAudit) Append(_ context.Context, e map[string]any) error {
	r.Entries = append(r.Entries, e)
	return nil
}

func mintToken(role, secret string) string {
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"role": role,
		"exp":  time.Now().Add(time.Hour).Unix(),
	})
	s, _ := tok.SignedString([]byte(secret))
	return s
}

func authedGet(url, token string) (*http.Response, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	return http.DefaultClient.Do(req)
}

func decodeJSON(t *testing.T, r io.Reader, dst any) {
	t.Helper()
	if err := json.NewDecoder(r).Decode(dst); err != nil {
		t.Fatal(err)
	}
}

func bodyContains(t *testing.T, r io.Reader, s string) {
	t.Helper()
	b, _ := io.ReadAll(r)
	if !strings.Contains(string(b), s) {
		t.Errorf("body=%q does not contain %q", b, s)
	}
}
