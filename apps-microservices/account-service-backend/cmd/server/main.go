// Command account-service is the centralized SSO + OAuth2 Authorization
// Server for the Hellopro platform. This entry point is intentionally thin:
// load config, initialise structured logging, hand the wiring to internal/app,
// then run the lifecycle. All dependency assembly + route registration live
// in the app package.
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/hellopro/account-service/internal/app"
	"github.com/hellopro/account-service/internal/config"
)

const version = "0.1.0"

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	cfg, err := config.Load()
	if err != nil {
		logger.Error("config load", "err", err)
		os.Exit(1)
	}

	a, err := app.Build(cfg, version)
	if err != nil {
		logger.Error("app build", "err", err)
		os.Exit(1)
	}

	stopChan := make(chan os.Signal, 1)
	signal.Notify(stopChan, os.Interrupt, syscall.SIGTERM)
	go func() {
		logger.Info("listening", "addr", a.Addr(), "version", version)
		if err := a.Run(); err != nil {
			logger.Error("listen", "err", err)
			os.Exit(1)
		}
	}()
	<-stopChan
	logger.Info("shutdown signal received")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := a.Shutdown(shutdownCtx); err != nil {
		logger.Error("shutdown", "err", err)
	}
	logger.Info("clean shutdown")
}
