package queue

import (
	"context"
	"encoding/json"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
)

// MatchesPattern vérifie si l'URL correspond au pattern glob-like.
// Traduit la logique matchesPattern() de server.js.
func MatchesPattern(rawURL, pattern string) bool {
	// Cas spécial : pattern de type extension avec @(...)
	if strings.Contains(pattern, "@(") {
		// Extrait les extensions du pattern @(ext1|ext2|...)
		start := strings.Index(pattern, "@(")
		end := strings.Index(pattern, ")")
		if start != -1 && end != -1 && end > start {
			exts := pattern[start+2 : end]
			re := regexp.MustCompile(`(?i)\.(?:` + exts + `)([?#].*)?$`)
			return re.MatchString(rawURL)
		}
		return false
	}

	// Supprime les globstars en tête/queue pour obtenir le motif "core"
	clean := pattern
	clean = strings.TrimPrefix(clean, "**/")
	clean = strings.TrimSuffix(clean, "/**")
	if strings.HasPrefix(clean, "**") {
		clean = clean[2:]
	}

	// Motif avec paramètre de requête (contient =) : inclusion simple
	if strings.Contains(clean, "=") {
		return strings.Contains(
			strings.ToLower(rawURL),
			strings.ToLower(strings.ReplaceAll(clean, "*", "")),
		)
	}

	// Échappe les caractères spéciaux regex (sauf *)
	escapedBase := regexp.QuoteMeta(strings.ReplaceAll(clean, "*", "\x00"))
	escapedBase = strings.ReplaceAll(escapedBase, "\x00", ".*")

	if strings.Contains(clean, "*") {
		// Motif glob avec wildcards internes
		re, err := regexp.Compile(`(?i)` + escapedBase)
		if err != nil {
			return false
		}
		return re.MatchString(rawURL)
	}

	// Motif de segment (ex: cart, login) — évite les faux positifs comme "cartouche"
	segmentRegex, err := regexp.Compile(`(?i)(^|[/?#&=.])` + escapedBase + `([/?#&=.]|$)`)
	if err != nil {
		return false
	}
	return segmentRegex.MatchString(rawURL)
}

// CleanPatterns parcourt tous les fichiers de la request queue pour le job donné,
// supprime ceux dont l'URL correspond à l'un des patterns fournis.
// Retourne le nombre de fichiers supprimés.
// Traduit server.js:1299-1367.
func CleanPatterns(ctx context.Context, storage *filestore.Storage, jobID string, patterns []string) (int, error) {
	baseDir := findRequestQueuesBase(storage, jobID)
	if baseDir == "" {
		return 0, nil
	}

	domainDirs, err := os.ReadDir(baseDir)
	if err != nil {
		return 0, err
	}

	deleted := 0
	for _, de := range domainDirs {
		if !de.IsDir() {
			continue
		}
		domainPath := filepath.Join(baseDir, de.Name())
		files, err := os.ReadDir(domainPath)
		if err != nil {
			continue
		}
		for _, f := range files {
			if f.IsDir() || !strings.HasSuffix(f.Name(), ".json") {
				continue
			}
			filePath := filepath.Join(domainPath, f.Name())
			raw, err := os.ReadFile(filePath)
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
			for _, pattern := range patterns {
				if MatchesPattern(data.URL, pattern) {
					_ = os.Remove(filePath)
					deleted++
					break
				}
			}
		}
	}
	return deleted, nil
}

// Repair parcourt les fichiers de la request queue pour le job donné.
// Supprime les fichiers dont le hostname de l'URL ne correspond pas au domaine du répertoire.
// Traduit server.js:772-823.
func Repair(ctx context.Context, storage *filestore.Storage, jobID string) (int, error) {
	baseDir := findRequestQueuesBase(storage, jobID)
	if baseDir == "" {
		return 0, nil
	}

	domainDirs, err := os.ReadDir(baseDir)
	if err != nil {
		return 0, err
	}

	deleted := 0
	for _, de := range domainDirs {
		if !de.IsDir() {
			continue
		}
		targetDomain := de.Name()
		domainPath := filepath.Join(baseDir, targetDomain)
		files, err := os.ReadDir(domainPath)
		if err != nil {
			continue
		}
		for _, f := range files {
			if f.IsDir() || !strings.HasSuffix(f.Name(), ".json") {
				continue
			}
			filePath := filepath.Join(domainPath, f.Name())
			raw, err := os.ReadFile(filePath)
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
			parsed, err := url.Parse(data.URL)
			if err != nil {
				// URL invalide : on laisse le fichier
				continue
			}
			hostname := parsed.Hostname()
			// Conserve si hostname == targetDomain ou si hostname se termine par "."+targetDomain
			if hostname != targetDomain && !strings.HasSuffix(hostname, "."+targetDomain) {
				_ = os.Remove(filePath)
				deleted++
			}
		}
	}
	return deleted, nil
}

// DropAll supprime tous les fichiers du répertoire request_queues du job donné.
// Recrée les sous-dossiers vides après suppression.
// Traduit server.js:826-861.
func DropAll(ctx context.Context, storage *filestore.Storage, jobID string) (int, error) {
	baseDir := findRequestQueuesBase(storage, jobID)
	if baseDir == "" {
		return 0, nil
	}

	domainDirs, err := os.ReadDir(baseDir)
	if err != nil {
		return 0, err
	}

	deleted := 0
	for _, de := range domainDirs {
		if !de.IsDir() {
			continue
		}
		domainPath := filepath.Join(baseDir, de.Name())
		files, err := os.ReadDir(domainPath)
		if err != nil {
			continue
		}
		for _, f := range files {
			if f.IsDir() {
				continue
			}
			filePath := filepath.Join(domainPath, f.Name())
			if err := os.Remove(filePath); err == nil {
				deleted++
			}
		}
	}
	return deleted, nil
}
