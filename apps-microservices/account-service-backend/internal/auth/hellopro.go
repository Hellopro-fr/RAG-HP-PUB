package auth

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

type HelloProAuthResponse struct {
	Success     bool   `json:"success"`
	Token       string `json:"token,omitempty"`
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
}

func AuthenticateHellopro(authURL, username, password string) (*HelloProAuthResponse, error) {
	parsed, err := url.Parse(authURL)
	if err != nil {
		return nil, fmt.Errorf("invalid auth URL: %w", err)
	}
	host := parsed.Hostname()
	if parsed.Scheme != "https" && host != "localhost" && host != "127.0.0.1" {
		return nil, fmt.Errorf("auth URL must use HTTPS (got %s)", parsed.Scheme)
	}

	form := url.Values{
		"login":    {username},
		"password": {password},
	}

	client := &http.Client{
		Timeout: 10 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	resp, err := client.PostForm(authURL, form)
	if err != nil {
		return nil, fmt.Errorf("auth request: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("auth returned status %d (body %d bytes)", resp.StatusCode, len(body))
	}
	var out HelloProAuthResponse
	if err := json.Unmarshal(body, &out); err != nil {
		return nil, fmt.Errorf("parse response: %w", err)
	}
	return &out, nil
}
