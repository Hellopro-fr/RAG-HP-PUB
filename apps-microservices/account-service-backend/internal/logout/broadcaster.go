package logout

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"time"
)

type DelivererConfig struct {
	Timeout     time.Duration
	MaxAttempts int
	BackoffBase time.Duration
}

type Deliverer struct {
	cfg DelivererConfig
	cli *http.Client
}

type DeliveryResult struct {
	Sent      bool
	Attempts  int
	LastError string
}

func NewDeliverer(cfg DelivererConfig) *Deliverer {
	if cfg.Timeout == 0 {
		cfg.Timeout = 5 * time.Second
	}
	if cfg.MaxAttempts == 0 {
		cfg.MaxAttempts = 3
	}
	if cfg.BackoffBase == 0 {
		cfg.BackoffBase = 1 * time.Second
	}
	return &Deliverer{
		cfg: cfg,
		cli: &http.Client{Timeout: cfg.Timeout},
	}
}

func (d *Deliverer) Deliver(url, secret string, body []byte) DeliveryResult {
	res := DeliveryResult{}
	wait := d.cfg.BackoffBase
	for attempt := 1; attempt <= d.cfg.MaxAttempts; attempt++ {
		res.Attempts = attempt
		req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
		if err != nil {
			res.LastError = err.Error()
			return res
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Logout-Signature", SignWebhook(secret, body))
		resp, err := d.cli.Do(req)
		if err != nil {
			res.LastError = err.Error()
		} else {
			io.Copy(io.Discard, resp.Body)
			resp.Body.Close()
			if resp.StatusCode >= 200 && resp.StatusCode < 300 {
				res.Sent = true
				return res
			}
			res.LastError = fmt.Sprintf("HTTP %d", resp.StatusCode)
			if resp.StatusCode >= 400 && resp.StatusCode < 500 {
				return res // 4xx: non-retryable
			}
		}
		if attempt < d.cfg.MaxAttempts {
			time.Sleep(wait)
			wait *= 2
		}
	}
	return res
}
