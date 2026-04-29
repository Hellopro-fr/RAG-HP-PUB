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
type AnalyzeDup struct {
	Total      int        `json:"total"`
	Unique     int        `json:"unique"`
	Duplicates int        `json:"duplicates"`
	ByURL      []DupGroup `json:"by_url"`
}

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
		ByURL: []DupGroup{},
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
		result.Total++
		urlMap[data.URL] = append(urlMap[data.URL], e.Name())
	}

	result.Unique = len(urlMap)

	// Construit les groupes de doublons (count > 1 seulement)
	for u, files := range urlMap {
		if len(files) > 1 {
			result.Duplicates += len(files) - 1
			result.ByURL = append(result.ByURL, DupGroup{
				URL:   u,
				Count: len(files),
				Files: files,
			})
		}
	}

	// Tri stable par URL pour des réponses reproductibles
	sort.Slice(result.ByURL, func(i, j int) bool {
		return result.ByURL[i].URL < result.ByURL[j].URL
	})

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
