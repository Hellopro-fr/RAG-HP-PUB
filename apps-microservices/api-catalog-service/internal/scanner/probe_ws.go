package scanner

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"
)

type WSEndpoint struct {
	Path    string
	Summary string
}

type APIInfo struct {
	WSEndpoints    []WSEndpoint
	GRPCAddress    string
	GRPCReflection bool
}

func ProbeAPIInfo(ctx context.Context, baseURL string, timeout time.Duration) APIInfo {
	url := strings.TrimRight(baseURL, "/") + "/api-info"
	cli := &http.Client{Timeout: timeout}
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return APIInfo{}
	}
	resp, err := cli.Do(req)
	if err != nil {
		return APIInfo{}
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return APIInfo{}
	}
	var raw struct {
		WS struct {
			Endpoints []struct {
				Path    string `json:"path"`
				Summary string `json:"summary"`
			} `json:"endpoints"`
		} `json:"ws"`
		GRPC struct {
			Address    string `json:"address"`
			Reflection bool   `json:"reflection"`
		} `json:"grpc"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		return APIInfo{}
	}
	info := APIInfo{GRPCAddress: raw.GRPC.Address, GRPCReflection: raw.GRPC.Reflection}
	for _, e := range raw.WS.Endpoints {
		info.WSEndpoints = append(info.WSEndpoints, WSEndpoint{Path: e.Path, Summary: e.Summary})
	}
	return info
}
