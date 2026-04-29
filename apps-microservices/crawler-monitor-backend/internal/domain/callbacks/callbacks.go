// Package callbacks gère les webhooks échoués stockés dans Redis.
//
// Structure des entrées dans la liste Redis `crawl_jobs:failed_callbacks` :
// {"webhook_type", "url", "params", "crawl_id", "error", "timestamp", "manual_retry_attempts"?}
//
// Les webhooks sont des requêtes HTTP GET (pas POST), conformément à la logique
// du crawler-service Python (httpx.get avec backoff exponentiel).
// Traduit src/lib/callbacks.js.
package callbacks

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

// Callback représente un webhook échoué stocké dans Redis.
type Callback struct {
	URL                 string            `json:"url"`
	Params              map[string]string `json:"params,omitempty"`
	WebhookType         string            `json:"webhook_type,omitempty"`
	CrawlID             string            `json:"crawl_id,omitempty"`
	Error               string            `json:"error,omitempty"`
	Timestamp           string            `json:"timestamp,omitempty"`
	ManualRetryAttempts int               `json:"manual_retry_attempts,omitempty"`
	Raw                 json.RawMessage   `json:"-"`
}

// ReplayResult contient le résultat d'une tentative de replay d'un callback.
type ReplayResult struct {
	OK     bool
	Status int
	Error  string
}

// BuildCallbackURL construit l'URL finale en ajoutant les params en query string.
// Préserve les query strings existants dans l'URL de base.
// Traduit buildCallbackUrl() de src/lib/callbacks.js.
func BuildCallbackURL(baseURL string, params map[string]string) (string, error) {
	u, err := url.Parse(baseURL)
	if err != nil {
		return "", fmt.Errorf("invalid base URL: %w", err)
	}
	if len(params) > 0 {
		q := u.Query()
		for k, v := range params {
			if v == "" {
				continue
			}
			q.Add(k, v)
		}
		u.RawQuery = q.Encode()
	}
	return u.String(), nil
}

// Replay rejoue un callback HTTP GET avec un timeout de 30s.
// Retourne un ReplayResult{OK, Status, Error}.
// Traduit replayCallback() de src/lib/callbacks.js.
func Replay(ctx context.Context, c Callback) ReplayResult {
	if c.URL == "" {
		return ReplayResult{OK: false, Error: "invalid_entry"}
	}

	finalURL, err := BuildCallbackURL(c.URL, c.Params)
	if err != nil {
		return ReplayResult{OK: false, Error: "invalid_url: " + err.Error()}
	}

	client := &http.Client{Timeout: 30 * time.Second}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, finalURL, nil)
	if err != nil {
		return ReplayResult{OK: false, Error: err.Error()}
	}

	resp, err := client.Do(req)
	if err != nil {
		// Vérifie si c'est un timeout de contexte
		if ctx.Err() == context.DeadlineExceeded {
			return ReplayResult{OK: false, Error: "timeout"}
		}
		return ReplayResult{OK: false, Error: err.Error()}
	}
	defer func() { _ = resp.Body.Close() }()
	// Consomme le corps pour libérer la connexion
	_, _ = io.Copy(io.Discard, resp.Body)

	ok := resp.StatusCode >= 200 && resp.StatusCode < 300
	errMsg := ""
	if !ok {
		errMsg = fmt.Sprintf("HTTP %d", resp.StatusCode)
	}
	return ReplayResult{OK: ok, Status: resp.StatusCode, Error: errMsg}
}
