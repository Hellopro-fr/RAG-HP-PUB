package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/joho/godotenv"
	"google.golang.org/grpc"

	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/config"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/db"
	pb "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/genproto/api_catalog"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/grpcserver"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/health"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/repository"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-catalog-service/internal/scanner"
)

// envURLPath is the seed-file path (mirrors api-gateway-go convention).
// Read once at boot and reloaded before every scan tick so SERVICE_*
// additions take effect without a container restart.
const envURLPath = ".env.url"

func reloadEnvURL() {
	if _, err := os.Stat(envURLPath); err == nil {
		_ = godotenv.Overload(envURLPath)
	}
}

func main() {
	reloadEnvURL()
	cfg := config.Load()

	g, err := db.Open(cfg.MySQLHost, cfg.MySQLPort, cfg.MySQLUser, cfg.MySQLPass, cfg.MySQLDB)
	if err != nil {
		log.Fatalf("open db: %v", err)
	}
	if err := db.AutoMigrate(g); err != nil {
		log.Fatalf("migrate: %v", err)
	}

	sr := repository.NewServiceRepo(g)
	er := repository.NewEndpointRepo(g)
	sc := scanner.New(scanner.Deps{Services: sr, Endpoints: er, Concurrency: cfg.ScanConcurrency, Timeout: cfg.ProbeTimeout})

	seeds := func() map[string]string {
		reloadEnvURL()
		return config.Load().SeedTargets
	}

	grpcSrv := grpc.NewServer(grpc.ChainUnaryInterceptor(
		grpcserver.NewLoggingInterceptor(),
		grpcserver.NewAdminInterceptor(cfg.AdminKey),
	))
	pb.RegisterApiCatalogServer(grpcSrv, grpcserver.NewServer(grpcserver.Deps{
		Services: sr, Endpoints: er, Scanner: sc, Seeds: seeds, AdminKey: cfg.AdminKey,
	}))

	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", cfg.GRPCPort))
	if err != nil {
		log.Fatalf("listen: %v", err)
	}

	httpSrv := &http.Server{
		Addr:    fmt.Sprintf(":%d", cfg.HealthPort),
		Handler: health.Handler(),
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go scanner.RunCron(ctx, sc, cfg.ScanInterval, seeds)
	go scanner.WatchFile(ctx, envURLPath, 500*time.Millisecond, func() {
		rep := sc.Run(ctx, seeds())
		log.Printf("scan (env.url change): scanned=%d ok=%d failed=%d", rep.ServicesScanned, rep.ServicesOK, rep.ServicesFailed)
	})

	go func() {
		log.Printf("gRPC listening on :%d", cfg.GRPCPort)
		if err := grpcSrv.Serve(lis); err != nil {
			log.Fatalf("grpc serve: %v", err)
		}
	}()
	go func() {
		log.Printf("health listening on :%d", cfg.HealthPort)
		if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("http: %v", err)
		}
	}()

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig
	log.Println("shutdown")
	cancel()
	grpcSrv.GracefulStop()
	sctx, scancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer scancel()
	_ = httpSrv.Shutdown(sctx)
}
