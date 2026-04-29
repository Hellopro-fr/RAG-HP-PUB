package benchmarks

import (
	"context"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/queue"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
)

func BenchmarkQueueAnalyze_10k(b *testing.B) {
	root := b.TempDir()
	if err := GenerateQueueFixture(root, "job1", 10000); err != nil {
		b.Fatal(err)
	}
	fs := filestore.New(root)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, err := queue.Analyze(context.Background(), fs, "job1")
		if err != nil {
			b.Fatal(err)
		}
	}
}

// Run with: go test -bench=BenchmarkQueueAnalyze_100k -benchtime=1x -timeout=10m ./tests/benchmarks/
func BenchmarkQueueAnalyze_100k(b *testing.B) {
	root := b.TempDir()
	if err := GenerateQueueFixture(root, "job1", 100000); err != nil {
		b.Fatal(err)
	}
	fs := filestore.New(root)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, err := queue.Analyze(context.Background(), fs, "job1")
		if err != nil {
			b.Fatal(err)
		}
	}
}
