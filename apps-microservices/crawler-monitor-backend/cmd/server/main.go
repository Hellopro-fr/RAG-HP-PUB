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

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/auditstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
)

var version = "dev"

func main() {
	if len(os.Args) >= 2 && os.Args[1] == "healthcheck" {
		os.Exit(runHealthcheck())
	}
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config.load", "err", err)
		os.Exit(1)
	}

	rs, err := redisstore.New(cfg.RedisURL)
	if err != nil {
		slog.Error("redis.connect", "err", err)
		os.Exit(1)
	}
	defer rs.Close()

	fs := filestore.New(cfg.CrawlerStoragePath)
	as := auditstore.New(cfg.AuditLogDir)

	r := httpapi.NewRouter(httpapi.Deps{
		Version:    version,
		Config:     cfg,
		RedisStore: rs,
		FileStore:  fs,
		AuditStore: httpapi.WrapAuditStore(as),
	})

	srv := &http.Server{
		Addr:              ":" + cfg.Port,
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
	_ = srv.Shutdown(shutdownCtx)
	slog.Info("server.shutdown.done")
}
