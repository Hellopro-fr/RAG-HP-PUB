package benchmarks

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

func GenerateQueueFixture(root, jobID string, n int) error {
	for i := 0; i < n; i++ {
		domain := fmt.Sprintf("example%d.com", i%50)
		dir := filepath.Join(root, jobID, "storage", "request_queues", domain)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return err
		}
		entry := map[string]any{
			"id":         fmt.Sprintf("r%d", i),
			"url":        fmt.Sprintf("https://%s/page/%d", domain, i),
			"method":     "GET",
			"orderNo":    int64(i + 1),
			"retryCount": 0,
			"uniqueKey":  fmt.Sprintf("https://%s/page/%d", domain, i),
		}
		b, _ := json.Marshal(entry)
		if err := os.WriteFile(filepath.Join(dir, fmt.Sprintf("%d.json", i)), b, 0o644); err != nil {
			return err
		}
	}
	return nil
}
