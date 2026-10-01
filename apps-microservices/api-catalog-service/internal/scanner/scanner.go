package scanner

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"github.com/google/uuid"
	"golang.org/x/sync/errgroup"

	"api-catalog-service/internal/db"
	"api-catalog-service/internal/repository"
)

type Deps struct {
	Services    *repository.ServiceRepo
	Endpoints   *repository.EndpointRepo
	Concurrency int
	Timeout     time.Duration
}

type Scanner struct{ d Deps }

func New(d Deps) *Scanner {
	if d.Concurrency <= 0 {
		d.Concurrency = 16
	}
	if d.Timeout <= 0 {
		d.Timeout = 3 * time.Second
	}
	return &Scanner{d: d}
}

type Report struct {
	ServicesScanned int
	ServicesOK      int
	ServicesFailed  int
	Errors          []string
	FinishedAt      time.Time
}

func (s *Scanner) Run(ctx context.Context, envSeeds map[string]string) Report {
	rows, _ := s.d.Services.ListAll()
	dbTargets := make([]DBRow, 0, len(rows))
	for _, r := range rows {
		dbTargets = append(dbTargets, DBRow{Name: r.Name, BaseURL: r.BaseURL, Source: r.Source})
	}
	targets := MergeTargets(envSeeds, dbTargets)

	var (
		mu  sync.Mutex
		rep Report
	)
	sem := make(chan struct{}, s.d.Concurrency)
	g, gctx := errgroup.WithContext(ctx)
	for _, t := range targets {
		t := t
		sem <- struct{}{}
		g.Go(func() error {
			defer func() { <-sem }()
			err := s.scanOne(gctx, t)
			mu.Lock()
			rep.ServicesScanned++
			if err == nil {
				rep.ServicesOK++
			} else {
				rep.ServicesFailed++
				rep.Errors = append(rep.Errors, fmt.Sprintf("%s: %v", t.Name, err))
			}
			mu.Unlock()
			return nil
		})
	}
	_ = g.Wait()
	rep.FinishedAt = time.Now().UTC()
	return rep
}

func (s *Scanner) scanOne(ctx context.Context, t Target) error {
	rest, _ := ProbeREST(ctx, t.BaseURL, s.d.Timeout)
	info := ProbeAPIInfo(ctx, t.BaseURL, s.d.Timeout)
	var grpcEps []db.EndpointRow
	if info.GRPCAddress != "" && info.GRPCReflection {
		grpcEps, _ = ProbeGRPC(ctx, info.GRPCAddress, s.d.Timeout)
	}

	var wsEps []db.EndpointRow
	for _, w := range info.WSEndpoints {
		wsEps = append(wsEps, db.EndpointRow{
			ID: uuid.NewString(), Protocol: "ws", Path: w.Path, Summary: w.Summary,
		})
	}

	protos := []string{}
	if len(rest) > 0 {
		protos = append(protos, "rest")
	}
	if len(wsEps) > 0 {
		protos = append(protos, "ws")
	}
	if len(grpcEps) > 0 {
		protos = append(protos, "grpc")
	}
	protosJSON, _ := json.Marshal(protos)

	now := time.Now().UTC()
	okFlag := true
	existing, err := s.d.Services.GetByName(t.Name)
	var serviceID string
	if err == repository.ErrNotFound {
		serviceID = uuid.NewString()
		row := &db.ServiceRow{
			ID: serviceID, Name: t.Name, BaseURL: t.BaseURL,
			Protocols: string(protosJSON), Source: t.Source, Status: "active",
			GRPCAddress:   info.GRPCAddress,
			LastScannedAt: &now, LastScanOK: &okFlag,
		}
		if err := s.d.Services.Create(row); err != nil {
			return err
		}
	} else if err != nil {
		return err
	} else {
		serviceID = existing.ID
		upd := map[string]any{
			"base_url":        t.BaseURL,
			"protocols":       string(protosJSON),
			"grpc_address":    info.GRPCAddress,
			"last_scanned_at": now,
			"last_scan_ok":    true,
			"last_scan_error": "",
		}
		if err := s.d.Services.Update(serviceID, upd); err != nil {
			return err
		}
	}

	all := append(append(rest, wsEps...), grpcEps...)
	for i := range all {
		all[i].ServiceID = serviceID
	}
	return s.d.Endpoints.ReplaceForService(serviceID, all)
}
