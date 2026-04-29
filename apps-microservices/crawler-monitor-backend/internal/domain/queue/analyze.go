package queue

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
)

// AnalyzeStats contient les statistiques agrégées d'une request queue.
// Mirrors server.js:871-881.
type AnalyzeStats struct {
	Total           int                 `json:"total"`
	Blocked         int                 `json:"blocked"`
	Valid           int                 `json:"valid"`
	Pending         int                 `json:"pending"`
	Handled         int                 `json:"handled"`
	Examples        AnalyzeExamples     `json:"examples"`
	BlockedPercent  any                 `json:"blockedPercent"`
	ValidPercent    any                 `json:"validPercent"`
	Recommendation  string              `json:"recommendation"`
}

// AnalyzeExamples contient des exemples d'URLs bloquées et valides (max 5 chacun).
// Mirrors server.js:877-880.
type AnalyzeExamples struct {
	Blocked []BlockedExample `json:"blocked"`
	Valid   []string         `json:"valid"`
}

// BlockedExample est une entrée dans examples.blocked.
// Mirrors server.js:911-914.
type BlockedExample struct {
	URL     string `json:"url"`
	Pattern string `json:"pattern"`
}

// domainFileStats accumule les stats pour un sous-répertoire de domaine.
type domainFileStats struct {
	total   int
	blocked int
	valid   int
	pending int
	handled int
	// Exemples — stockés séparément, fusionnés ensuite
	exBlocked []BlockedExample
	exValid   []string
}

// Analyze parcourt toutes les request queue files du job donné, applique BlockedPatterns
// et retourne les statistiques agrégées.
// Parallélise par domaine (goroutines limitées à 8) — mirrors server.js:863-964.
//
// Retourne une réponse vide (total=0) si le répertoire n'existe pas.
func Analyze(ctx context.Context, storage *filestore.Storage, jobID string) (*AnalyzeStats, error) {
	baseDir := findRequestQueuesBase(storage, jobID)
	if baseDir == "" {
		return emptyAnalyzeStats(), nil
	}

	domainEntries, err := os.ReadDir(baseDir)
	if err != nil {
		return emptyAnalyzeStats(), nil
	}

	// Filtre uniquement les sous-répertoires (domaines)
	var domainDirs []os.DirEntry
	for _, de := range domainEntries {
		if de.IsDir() {
			domainDirs = append(domainDirs, de)
		}
	}

	if len(domainDirs) == 0 {
		return emptyAnalyzeStats(), nil
	}

	const maxWorkers = 8

	type result struct {
		stats domainFileStats
		err   error
	}

	results := make([]domainFileStats, len(domainDirs))
	errs := make([]error, len(domainDirs))

	sem := make(chan struct{}, maxWorkers)
	var wg sync.WaitGroup

	for i, de := range domainDirs {
		wg.Add(1)
		go func(idx int, entry os.DirEntry) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()

			r := result{}
			r.stats, r.err = analyzeDirectory(filepath.Join(baseDir, entry.Name()))
			results[idx] = r.stats
			errs[idx] = r.err
		}(i, de)
	}
	wg.Wait()

	// Agrège les résultats de tous les domaines
	agg := &AnalyzeStats{
		Examples: AnalyzeExamples{
			Blocked: []BlockedExample{},
			Valid:   []string{},
		},
	}

	for _, s := range results {
		agg.Total += s.total
		agg.Blocked += s.blocked
		agg.Valid += s.valid
		agg.Pending += s.pending
		agg.Handled += s.handled

		// Fusionne les exemples (max 5 global pour chaque catégorie)
		for _, ex := range s.exBlocked {
			if len(agg.Examples.Blocked) < 5 {
				agg.Examples.Blocked = append(agg.Examples.Blocked, ex)
			}
		}
		for _, ex := range s.exValid {
			if len(agg.Examples.Valid) < 5 {
				agg.Examples.Valid = append(agg.Examples.Valid, ex)
			}
		}
	}

	// Calcul des pourcentages (mirrors server.js:947-949)
	if agg.Total > 0 {
		agg.BlockedPercent = fmt.Sprintf("%.1f", float64(agg.Blocked)/float64(agg.Total)*100)
		agg.ValidPercent = fmt.Sprintf("%.1f", float64(agg.Valid)/float64(agg.Total)*100)
	} else {
		agg.BlockedPercent = "0"
		agg.ValidPercent = "0"
	}

	// Recommandation (mirrors server.js:951-958)
	blockedPct := 0.0
	if agg.Total > 0 {
		blockedPct = float64(agg.Blocked) / float64(agg.Total) * 100
	}
	switch {
	case blockedPct > 90:
		agg.Recommendation = `Use "Clean Patterns" to remove blocked URLs`
	case agg.Valid == 0:
		agg.Recommendation = "Safe to drop entire queue (no valid URLs)"
	default:
		agg.Recommendation = `Use "Clean Patterns" to preserve valid URLs`
	}

	return agg, nil
}

// analyzeDirectory traite tous les fichiers JSON d'un sous-répertoire de domaine.
func analyzeDirectory(dir string) (domainFileStats, error) {
	files, err := os.ReadDir(dir)
	if err != nil {
		return domainFileStats{}, err
	}

	var s domainFileStats

	for _, f := range files {
		if f.IsDir() || !strings.HasSuffix(f.Name(), ".json") {
			continue
		}

		raw, err := os.ReadFile(filepath.Join(dir, f.Name()))
		if err != nil {
			continue
		}

		var data crawleeFile
		if err := json.Unmarshal(raw, &data); err != nil {
			continue
		}

		if data.URL == "" {
			continue
		}

		s.total++

		// Catégorisation URL bloquée vs valide (mirrors server.js:900-927)
		isBlocked := false
		matchedPattern := ""
		for _, pattern := range BlockedPatterns {
			if MatchesPattern(data.URL, pattern) {
				isBlocked = true
				matchedPattern = pattern
				s.blocked++
				if len(s.exBlocked) < 5 {
					s.exBlocked = append(s.exBlocked, BlockedExample{URL: data.URL, Pattern: matchedPattern})
				}
				break
			}
		}

		if !isBlocked {
			s.valid++
			if len(s.exValid) < 5 {
				s.exValid = append(s.exValid, data.URL)
			}
		}

		// Détection handled : orderNo == null (mirrors server.js:929-937)
		if data.OrderNo == nil {
			s.handled++
		} else {
			s.pending++
		}
	}

	return s, nil
}

// emptyAnalyzeStats retourne une réponse vide cohérente.
func emptyAnalyzeStats() *AnalyzeStats {
	return &AnalyzeStats{
		Total:          0,
		Blocked:        0,
		Valid:          0,
		Pending:        0,
		Handled:        0,
		Examples:       AnalyzeExamples{Blocked: []BlockedExample{}, Valid: []string{}},
		BlockedPercent: "0",
		ValidPercent:   "0",
		Recommendation: `Use "Clean Patterns" to preserve valid URLs`,
	}
}
