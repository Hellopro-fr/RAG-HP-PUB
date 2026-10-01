package config

import (
	"log"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	MySQLHost       string
	MySQLPort       string
	MySQLUser       string
	MySQLPass       string
	MySQLDB         string
	GRPCPort        int
	HealthPort      int
	AdminKey        string
	ScanInterval    time.Duration
	ScanConcurrency int
	ProbeTimeout    time.Duration
	SeedTargets     map[string]string
}

func Load() Config {
	cfg := Config{
		MySQLHost:       getenv("MYSQL_HOST", "gateway-mysql"),
		MySQLPort:       getenv("MYSQL_PORT", "3306"),
		MySQLUser:       getenv("MYSQL_USER", "catalog_user"),
		MySQLPass:       os.Getenv("MYSQL_PASS"),
		MySQLDB:         getenv("MYSQL_DB", "catalog_db"),
		GRPCPort:        getenvInt("GRPC_PORT", 9100),
		HealthPort:      getenvInt("HEALTH_PORT", 9101),
		AdminKey:        os.Getenv("ADMIN_KEY"),
		ScanInterval:    getenvDuration("SCAN_INTERVAL", 15*time.Minute),
		ScanConcurrency: getenvInt("SCAN_CONCURRENCY", 16),
		ProbeTimeout:    getenvDuration("PROBE_TIMEOUT", 3*time.Second),
		SeedTargets:     buildSeedTargets(),
	}
	if cfg.MySQLPass == "" {
		log.Println("WARN: MYSQL_PASS empty")
	}
	if cfg.AdminKey == "" {
		log.Println("WARN: ADMIN_KEY empty (write RPCs will reject all)")
	}
	return cfg
}

func buildSeedTargets() map[string]string {
	out := map[string]string{}
	for _, kv := range os.Environ() {
		eq := strings.IndexByte(kv, '=')
		if eq <= 0 {
			continue
		}
		k, v := kv[:eq], kv[eq+1:]
		if !strings.HasPrefix(k, "SERVICE_") {
			continue
		}
		name := strings.ToLower(strings.TrimPrefix(k, "SERVICE_"))
		out[name+"-service"] = v
	}
	return out
}

func getenv(k, def string) string {
	if v, ok := os.LookupEnv(k); ok && v != "" {
		return v
	}
	return def
}

func getenvInt(k string, def int) int {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
}

func getenvDuration(k string, def time.Duration) time.Duration {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return def
	}
	return d
}
