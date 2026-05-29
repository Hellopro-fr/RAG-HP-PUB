// Package proxy forwards JSON-RPC bodies to an upstream MCP server.
package proxy

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"time"
)

// ForwardJSONRPC issues POST <upstreamURL> with the given headers and body,
// applying timeout as the per-call deadline. Returns the upstream response
// body as an io.ReadCloser; the caller is responsible for closing it.
func ForwardJSONRPC(ctx context.Context, upstreamURL string, headers map[string]string, body io.Reader, timeout time.Duration) (io.ReadCloser, error) {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	// The cancel is intentionally NOT deferred here — the caller owns the
	// response lifetime. We attach the cancel to the response body so closing
	// the body cancels the context (see closeWithCancel below).
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, upstreamURL, body)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		cancel()
		return nil, fmt.Errorf("upstream POST: %w", err)
	}
	return &closeWithCancel{ReadCloser: resp.Body, cancel: cancel}, nil
}

// closeWithCancel wires the context cancel onto the response Close so callers
// release both at once.
type closeWithCancel struct {
	io.ReadCloser
	cancel context.CancelFunc
}

func (c *closeWithCancel) Close() error {
	err := c.ReadCloser.Close()
	c.cancel()
	return err
}
