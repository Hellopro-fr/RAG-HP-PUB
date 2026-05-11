package main

import (
	"context"
	"encoding/gob"
	"log"
	"runtime"
	"time"

	"github.com/gin-contrib/sessions"
	"github.com/gin-contrib/sessions/cookie"
	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"

	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/auth"
	cachepkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/cache"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/config"
	dbpkg "github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/db"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/openapi"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/proxy"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/routers"
	"github.com/Hellopro-fr/rag-hp-pub/apps-microservices/api-gateway-go/internal/sso"
)

func init() {
	// Required so gin-contrib/sessions cookie store can serialize the
	// session.user map[string]any (and its nested sso map).
	gob.Register(map[string]any{})
}

func main() {
	// Mirror api-gateway (Python) settings.py:
	//   load_dotenv(".env")
	//   if Path(".env.url").exists(): load_dotenv(".env.url", override=True)
	_ = godotenv.Load()
	_ = godotenv.Overload(".env.url")
	cfg := config.Load()

	ctx := context.Background()
	dsn := dbpkg.BuildDSN(cfg.MySQLUser, cfg.MySQLPass, cfg.MySQLHost, cfg.MySQLPort, cfg.MySQLDB)
	gdb, err := dbpkg.Open(ctx, dsn)
	if err != nil {
		log.Fatalf("db open: %v", err)
	}
	if err := dbpkg.AutoMigrate(gdb); err != nil {
		log.Fatalf("automigrate: %v", err)
	}

	rdb, err := cachepkg.OpenFromURL(cfg.RedisURL)
	if err != nil {
		log.Fatalf("redis open: %v", err)
	}
	cache := cachepkg.New(rdb)

	jwtSvc := auth.NewJWT(cfg.JWTSecret, cfg.JWTAlgo, time.Duration(cfg.AccessTokenExpireMinutes)*time.Minute)

	serviceMap := config.BuildServiceMap()

	if err := dbpkg.BootstrapRefreshTokens(ctx, gdb, serviceMap, jwtIssuerAdapter{j: jwtSvc}); err != nil {
		log.Fatalf("bootstrap refresh tokens: %v", err)
	}

	historyWorkers := runtime.NumCPU() / 2
	if historyWorkers < 2 {
		historyWorkers = 2
	}
	historyWorker := proxy.NewHistoryWorker(gdb, config.ExcludedServices(), 1024, historyWorkers)
	historyWorker.Start()
	defer historyWorker.Stop()

	r := gin.New()
	r.Use(gin.Recovery())
	r.Use(sessions.Sessions("session", cookie.NewStore([]byte(cfg.JWTSecret))))
	r.Use(auth.DocsAuthMiddleware(jwtSvc))

	resolver := sso.NewResolver(sso.ResolverConfig{ServiceName: cfg.ServiceName, AccountBaseURL: cfg.AccountBaseURL})
	routers.RegisterSSO(r, routers.SSODeps{
		Resolver:        resolver,
		AccountBaseURL:  cfg.AccountBaseURL,
		AccountPubURL:   cfg.AccountPublicURL,
		AccountRedirect: cfg.AccountRedirectURI,
		SecureCookie:    cfg.SecureCookie,
	})
	routers.RegisterLogin(r, jwtSvc)
	routers.RegisterTokens(r, routers.TokenDeps{
		DB:                       gdb,
		Cache:                    cache,
		JWT:                      jwtSvc,
		AdminKey:                 cfg.GatewayAdminKey,
		AccessTokenExpireMinutes: cfg.AccessTokenExpireMinutes,
	})

	baseSpec, err := openapi.LoadBaseSpec()
	if err != nil {
		log.Fatalf("parse base.yaml: %v", err)
	}
	adminEmails := map[string]struct{}{}
	for _, e := range cfg.DocsAdminEmails {
		adminEmails[e] = struct{}{}
	}
	routers.RegisterDocs(r, routers.DocsDeps{
		BaseSpec:    baseSpec,
		ServiceMap:  serviceMap,
		AdminEmails: adminEmails,
		AdminKey:    cfg.GatewayAdminKey,
	})

	verifier := auth.NewAPITokenVerifier(jwtSvc, gdb, cache, config.BuildExcludedRoutes())
	wsHandler := proxy.NewWSHandler(serviceMap)
	httpHandler := proxy.NewHTTPHandler(proxy.HTTPDeps{
		ServiceMap:        serviceMap,
		DownstreamTimeout: config.BuildDownstreamTimeouts(),
		History:           historyWorker,
	})

	// Order matters: wsHandler short-circuits on WebSocket upgrade requests
	// (no auth enforced on WS — matches Python). Non-WS requests fall through
	// to verifier + httpHandler.
	r.Any("/:service/*path",
		wsHandler,
		verifier.Middleware(),
		httpHandler,
	)

	addr := ":8500"
	log.Printf("api-gateway-go listening on %s", addr)
	if err := r.Run(addr); err != nil {
		log.Fatalf("listen: %v", err)
	}
}

type jwtIssuerAdapter struct{ j *auth.JWT }

func (a jwtIssuerAdapter) NewRefreshToken(service string) string {
	return a.j.GenerateRefreshToken(service)
}
