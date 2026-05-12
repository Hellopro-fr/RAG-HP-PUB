// Package main is the entry point for mcp-zoho-service.
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"mcp-zoho-service/internal/config"
	"mcp-zoho-service/internal/crypto"
	"mcp-zoho-service/internal/db"
	"mcp-zoho-service/internal/routing"
	"mcp-zoho-service/internal/transport"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("[mcp-zoho-service] config: %v", err)
	}

	dec, err := crypto.NewDecryptor(cfg.EncryptionKey)
	if err != nil {
		log.Fatalf("[mcp-zoho-service] crypto: %v", err)
	}

	conn, err := db.Open(cfg.MySQLDSN)
	if err != nil {
		log.Fatalf("[mcp-zoho-service] db: %v", err)
	}
	defer conn.Close()

	queries := db.NewQueries(conn)
	resolver := routing.NewResolver(queries, dec, cfg.CacheTTL, cfg.SelfURL)
	srv := &transport.Server{
		Resolver:        resolver,
		UpstreamTimeout: cfg.UpstreamTimeout,
		GatewayToken:    cfg.GatewayToken,
	}
	httpSrv := srv.MustListen(fmt.Sprintf(":%d", cfg.Port))

	go func() {
		log.Printf("[mcp-zoho-service] listening on :%d", cfg.Port)
		if err := httpSrv.ListenAndServe(); err != nil && err.Error() != "http: Server closed" {
			log.Fatalf("[mcp-zoho-service] http: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	log.Printf("[mcp-zoho-service] shutting down")
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := httpSrv.Shutdown(ctx); err != nil {
		log.Printf("[mcp-zoho-service] shutdown: %v", err)
	}
}
