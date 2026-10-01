package scanner

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"

	"api-catalog-service/internal/db"
)

func ProbeREST(ctx context.Context, baseURL string, timeout time.Duration) ([]db.EndpointRow, error) {
	url := strings.TrimRight(baseURL, "/") + "/openapi.json"
	cli := &http.Client{Timeout: timeout}
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := cli.Do(req)
	if err != nil {
		return nil, nil
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, nil
	}
	var spec struct {
		Paths map[string]map[string]struct {
			OperationID string   `json:"operationId"`
			Summary     string   `json:"summary"`
			Tags        []string `json:"tags"`
			Deprecated  bool     `json:"deprecated"`
		} `json:"paths"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&spec); err != nil {
		return nil, nil
	}
	methods := []string{"get", "post", "put", "delete", "patch", "options", "head"}
	var out []db.EndpointRow
	for path, pmap := range spec.Paths {
		for _, m := range methods {
			op, ok := pmap[m]
			if !ok {
				continue
			}
			tags, _ := json.Marshal(op.Tags)
			out = append(out, db.EndpointRow{
				ID:          uuid.NewString(),
				Protocol:    "rest",
				Method:      strings.ToUpper(m),
				Path:        path,
				Summary:     op.Summary,
				OperationID: op.OperationID,
				Tags:        string(tags),
				Deprecated:  op.Deprecated,
			})
		}
	}
	return out, nil
}
