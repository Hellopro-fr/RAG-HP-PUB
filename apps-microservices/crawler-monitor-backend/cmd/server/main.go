package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
)

var version = "dev"

func main() {
	if len(os.Args) >= 2 && os.Args[1] == "healthcheck" {
		os.Exit(runHealthcheck())
	}

	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	port := os.Getenv("PORT")
	if port == "" {
		port = "3001"
	}

	r := httpapi.NewRouter(httpapi.Deps{Version: version})

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           r,
		ReadHeaderTimeout: 10 * time.Second,
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	go func() {
		slog.Info("server.start", "addr", srv.Addr, "version", version)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("server.listen", "err", err)
			os.Exit(1)
		}
	}()

	<-ctx.Done()
	slog.Info("server.shutdown.start")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		slog.Error("server.shutdown", "err", err)
		os.Exit(1)
	}
	slog.Info("server.shutdown.done")
}
