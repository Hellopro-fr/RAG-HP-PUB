package scanner

import (
	"context"
	"log"
	"time"
)

func RunCron(ctx context.Context, s *Scanner, interval time.Duration, seeds func() map[string]string) {
	log.Printf("scanner cron started, interval=%s (initial scan now)", interval)
	if s != nil {
		rep := s.Run(ctx, seeds())
		log.Printf("scan boot: scanned=%d ok=%d failed=%d", rep.ServicesScanned, rep.ServicesOK, rep.ServicesFailed)
	}

	t := time.NewTicker(interval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			rep := s.Run(ctx, seeds())
			log.Printf("scan tick: scanned=%d ok=%d failed=%d", rep.ServicesScanned, rep.ServicesOK, rep.ServicesFailed)
		}
	}
}
