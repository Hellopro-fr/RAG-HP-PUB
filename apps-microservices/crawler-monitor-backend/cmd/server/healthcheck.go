package main

import (
	"net/http"
	"os"
	"time"
)

func runHealthcheck() int {
	port := os.Getenv("PORT")
	if port == "" {
		port = "3001"
	}
	c := &http.Client{Timeout: 3 * time.Second}
	resp, err := c.Get("http://127.0.0.1:" + port + "/health")
	if err != nil {
		return 1
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return 1
	}
	return 0
}
