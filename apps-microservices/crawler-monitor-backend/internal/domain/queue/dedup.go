package queue

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
)

// DupGroup représente un groupe de fichiers partageant la même URL (count > 1).
type DupGroup struct {
	URL   string   `json:"url"`
	Count int      `json:"count"`
	Files []string `json:"files"`
}

// AnalyzeDup contient le résultat de l'analyse des doublons pour un dataset.
// Field names mirrent server.js:1206-1212 (totalItems/uniqueUrls/duplicateCount/
// duplicatesExample) — le frontend (`DuplicatesTab.jsx:24-38`) lit ces noms.
// `by_url` est conservé en plus comme champ Go-only borné (cf. dupExampleMax)
// pour éviter de renvoyer des dizaines de MB qui font crasher le frontend
// avec un `Maximum call stack size exceeded` durant la React Query structural
// sharing.
type AnalyzeDup struct {
	TotalItems        int        `json:"totalItems"`
	UniqueUrls        int        `json:"uniqueUrls"`
	DuplicateCount    int        `json:"duplicateCount"`
	DuplicatesExample []string   `json:"duplicatesExample"`
	ByURL             []DupGroup `json:"by_url"`
}

// dupExampleMax limite le nombre d'URLs en exemple + le nombre de groupes
// renvoyés en détail. Express ne renvoyait que 5 exemples ; on conserve la
// liste des groupes pour les jobs de petite taille mais on coupe au-delà.
const dupExampleMax = 5
const dupGroupsMax = 200

// rawEntry est la forme minimale attendue dans les fichiers JSON de dataset.
type rawEntry struct {
	URL string `json:"url"`
}

// AnalyzeDuplicates scanne le dataset principal (success) du job donné,
// groupe les fichiers par URL et retourne uniquement les groupes avec count > 1.
// Traduit server.js:1139-1212.
func AnalyzeDuplicates(ctx context.Context, storage *filestore.Storage, jobID string) (*AnalyzeDup, error) {
	dirs := listDatasetDirs(ctx, storage, jobID)
	dir := dirs.mainDir

	result := &AnalyzeDup{
		DuplicatesExample: []string{},
		ByURL:             []DupGroup{},
	}

	if dir == "" {
		return result, nil
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		return result, nil
	}

	// urlMap : URL → liste de noms de fichiers
	urlMap := make(map[string][]string)

	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		filePath := filepath.Join(dir, e.Name())
		raw, err := os.ReadFile(filePath)
		if err != nil {
			continue
		}
		var data rawEntry
		if err := json.Unmarshal(raw, &data); err != nil || data.URL == "" {
			continue
		}
		result.TotalItems++
		urlMap[data.URL] = append(urlMap[data.URL], e.Name())
	}

	result.UniqueUrls = len(urlMap)

	// Construit les groupes de doublons (count > 1 seulement)
	for u, files := range urlMap {
		if len(files) > 1 {
			result.DuplicateCount += len(files) - 1
			result.ByURL = append(result.ByURL, DupGroup{
				URL:   u,
				Count: len(files),
				Files: files,
			})
			if len(result.DuplicatesExample) < dupExampleMax {
				result.DuplicatesExample = append(result.DuplicatesExample, u)
			}
		}
	}

	// Tri stable par URL pour des réponses reproductibles
	sort.Slice(result.ByURL, func(i, j int) bool {
		return result.ByURL[i].URL < result.ByURL[j].URL
	})
	// Cap pour ne jamais renvoyer un payload qui fait exploser React Query.
	if len(result.ByURL) > dupGroupsMax {
		result.ByURL = result.ByURL[:dupGroupsMax]
	}

	return result, nil
}

// DeduplicateDataset supprime les doublons dans le dataset principal (success) du job donné.
// Pour chaque groupe de fichiers partageant la même URL, conserve le fichier avec le mtime
// le plus récent (newest) et supprime les autres.
// Retourne le nombre de fichiers supprimés.
// Traduit server.js:1214-1297.
func DeduplicateDataset(ctx context.Context, storage *filestore.Storage, jobID string) (int, error) {
	dirs := listDatasetDirs(ctx, storage, jobID)
	dir := dirs.mainDir

	if dir == "" {
		return 0, nil
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		return 0, nil
	}

	type fileEntry struct {
		name  string
		path  string
		mtime int64
	}

	// urlFilesMap : URL → liste de fileEntry
	urlFilesMap := make(map[string][]fileEntry)

	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		filePath := filepath.Join(dir, e.Name())
		raw, err := os.ReadFile(filePath)
		if err != nil {
			continue
		}
		var data rawEntry
		if err := json.Unmarshal(raw, &data); err != nil || data.URL == "" {
			continue
		}
		info, err := os.Stat(filePath)
		if err != nil {
			continue
		}
		urlFilesMap[data.URL] = append(urlFilesMap[data.URL], fileEntry{
			name:  e.Name(),
			path:  filePath,
			mtime: info.ModTime().UnixMilli(),
		})
	}

	deleted := 0
	for _, files := range urlFilesMap {
		if len(files) <= 1 {
			continue
		}
		// Trie par mtime décroissant (le plus récent en premier)
		sort.Slice(files, func(i, j int) bool {
			return files[i].mtime > files[j].mtime
		})
		// Conserve le premier (le plus récent), supprime les autres
		for _, f := range files[1:] {
			if err := os.Remove(f.path); err == nil {
				deleted++
			}
		}
	}
	return deleted, nil
}
