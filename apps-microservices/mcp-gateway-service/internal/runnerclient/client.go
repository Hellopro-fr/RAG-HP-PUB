package runnerclient

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type Client struct {
	baseURL    string
	adminToken string
	http       *http.Client
}

func New(baseURL, adminToken string) *Client {
	// http.Client has no overall Timeout — per-call deadlines are enforced via
	// context.WithTimeout in each method (Spawn=30s, Kill/Restart/List=15s,
	// Reconcile=60s). A shared http.Client.Timeout would clip the longer calls.
	return &Client{
		baseURL:    baseURL,
		adminToken: adminToken,
		http:       &http.Client{},
	}
}

func (c *Client) do(ctx context.Context, method, path string, body any, out any) error {
	var reader *bytes.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("encode: %w", err)
		}
		reader = bytes.NewReader(b)
	}
	var req *http.Request
	var err error
	if reader != nil {
		req, err = http.NewRequestWithContext(ctx, method, c.baseURL+path, reader)
	} else {
		req, err = http.NewRequestWithContext(ctx, method, c.baseURL+path, nil)
	}
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Admin-Token", c.adminToken)

	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("runner %s %s: %w", method, path, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		var errBody map[string]any
		_ = json.NewDecoder(resp.Body).Decode(&errBody)
		return fmt.Errorf("runner %s %s: status %d: %v", method, path, resp.StatusCode, errBody)
	}
	if out != nil {
		return json.NewDecoder(resp.Body).Decode(out)
	}
	return nil
}

func (c *Client) Spawn(req SpawnRequest) (*SpawnResponse, error) {
	var out SpawnResponse
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err := c.do(ctx, http.MethodPost, "/admin/instances", req, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) Kill(instanceID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	return c.do(ctx, http.MethodDelete, "/admin/instances/"+instanceID, nil, nil)
}

func (c *Client) Restart(instanceID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	return c.do(ctx, http.MethodPost, "/admin/instances/"+instanceID+"/restart", nil, nil)
}

func (c *Client) List() ([]InstanceStatus, error) {
	var out struct {
		Instances []InstanceStatus `json:"instances"`
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := c.do(ctx, http.MethodGet, "/admin/instances", nil, &out); err != nil {
		return nil, err
	}
	return out.Instances, nil
}

func (c *Client) Reconcile(desired []SpawnRequest) error {
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	return c.do(ctx, http.MethodPost, "/admin/reconcile", ReconcileRequest{DesiredInstances: desired}, nil)
}
