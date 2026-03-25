package orchestrator

import (
	"context"
	"fmt"
	"log"
	"strings"
	"sync"
	"time"

	databasepb "github.com/hellopro/mcp-api-recherche/proto/gen/database"
)

// Milvus DataType values (matching pymilvus DataType enum).
const (
	dtBool    = "BOOL"
	dtInt8    = "INT8"
	dtInt16   = "INT16"
	dtInt32   = "INT32"
	dtInt64   = "INT64"
	dtFloat   = "FLOAT"
	dtDouble  = "DOUBLE"
	dtVarChar = "VARCHAR"
	dtArray   = "ARRAY"
	dtJSON    = "JSON"
)

var numericTypes = map[string]bool{
	dtInt8: true, dtInt16: true, dtInt32: true, dtInt64: true,
	dtFloat: true, dtDouble: true,
}

var intTypes = map[string]bool{
	dtInt8: true, dtInt16: true, dtInt32: true, dtInt64: true,
}

var pageTypeSiteweb = map[string]bool{
	"home": true, "listing_produit": true, "fiche_produit": true,
	"fiche_realisation": true, "presentation_societe": true, "contact": true,
	"cgv_mentions_legales_cgu": true, "article": true, "savoir_faire": true,
	"page_local": true, "demande_devis": true, "compte_client": true,
	"recrutement": true, "references_clients": true, "faq": true,
	"plan_du_site": true, "politique_confidentialite": true, "autre": true,
}

// SchemaCache caches collection schemas with a TTL.
type SchemaCache struct {
	mu      sync.RWMutex
	entries map[string]*schemaCacheEntry
	ttl     time.Duration
}

type schemaCacheEntry struct {
	fields    map[string]string
	fetchedAt time.Time
}

func NewSchemaCache(ttl time.Duration) *SchemaCache {
	return &SchemaCache{
		entries: make(map[string]*schemaCacheEntry),
		ttl:     ttl,
	}
}

func (sc *SchemaCache) Get(collection string) (map[string]string, bool) {
	sc.mu.RLock()
	defer sc.mu.RUnlock()
	entry, ok := sc.entries[collection]
	if !ok || time.Since(entry.fetchedAt) > sc.ttl {
		return nil, false
	}
	return entry.fields, true
}

func (sc *SchemaCache) Set(collection string, fields map[string]string) {
	sc.mu.Lock()
	defer sc.mu.Unlock()
	sc.entries[collection] = &schemaCacheEntry{
		fields:    fields,
		fetchedAt: time.Now(),
	}
}

// FilterBuilder constructs Milvus filter expressions.
type FilterBuilder struct {
	dbClient    databasepb.DatabaseSearchServiceClient
	schemaCache *SchemaCache
}

func NewFilterBuilder(dbClient databasepb.DatabaseSearchServiceClient, cache *SchemaCache) *FilterBuilder {
	return &FilterBuilder{
		dbClient:    dbClient,
		schemaCache: cache,
	}
}

// Build constructs filter clauses for a given source and filters.
func (fb *FilterBuilder) Build(ctx context.Context, filtre map[string]any, source string) (string, error) {
	fieldTypes, err := fb.getFieldTypes(ctx, source)
	if err != nil {
		log.Printf("[filter] could not get schema for %s: %v", source, err)
		return "", nil
	}
	if len(fieldTypes) == 0 {
		return "", nil
	}

	var clauses []string
	for key, val := range filtre {
		dtype := fieldTypes[key]

		// Special cases matching the Python FilterBuilder
		if key == "id_categorie" && source == "produits" {
			key = "categorie"
		} else if key == "id_categorie" && source == "siteweb" {
			continue
		} else if key == "autre_chunks" && source == "prix" {
			continue
		} else if key == "avec_prix" && (source == "produits_4" || source == "produits_3") {
			if boolVal, ok := val.(bool); ok && boolVal {
				clauses = append(clauses, "(prix_ht != '' OR prix_ttc != '')")
			}
			continue
		}

		if dtype == "" {
			continue
		}

		var clause string
		if dtype == dtArray {
			clause = buildArrayClause(key, val)
		} else if numericTypes[dtype] {
			clause = buildNumericClause(key, val, dtype)
		} else {
			clause = buildStringClause(key, val, source)
		}
		if clause != "" {
			clauses = append(clauses, clause)
		}
	}

	return strings.Join(clauses, " and "), nil
}

func (fb *FilterBuilder) getFieldTypes(ctx context.Context, collection string) (map[string]string, error) {
	if fields, ok := fb.schemaCache.Get(collection); ok {
		return fields, nil
	}

	resp, err := fb.dbClient.GetSchema(ctx, &databasepb.GetSchemaRequest{
		CollectionName: collection,
		SourceService:  strPtr("mcp-api-recherche"),
	})
	if err != nil {
		return nil, err
	}

	fields := resp.GetFields()
	if len(fields) > 0 {
		fb.schemaCache.Set(collection, fields)
	}
	return fields, nil
}

func buildArrayClause(key string, val any) string {
	switch v := val.(type) {
	case []any:
		if len(v) == 0 {
			return ""
		}
		subs := make([]string, 0, len(v))
		for _, item := range v {
			subs = append(subs, fmt.Sprintf("array_contains(%s, '%v')", key, item))
		}
		return "(" + strings.Join(subs, " or ") + ")"
	default:
		return fmt.Sprintf("array_contains(%s, '%v')", key, val)
	}
}

func buildNumericClause(key string, val any, dtype string) string {
	if m, ok := val.(map[string]any); ok {
		if _, hasOp := m["operator"]; hasOp {
			return buildOperatorClause(key, m)
		}
	}

	switch v := val.(type) {
	case []any:
		vals := make([]string, 0, len(v))
		for _, item := range v {
			vals = append(vals, castNumericStr(item, dtype))
		}
		return fmt.Sprintf("%s in [%s]", key, strings.Join(vals, ", "))
	default:
		return fmt.Sprintf("%s == %s", key, castNumericStr(val, dtype))
	}
}

func buildStringClause(key string, val any, source string) string {
	if m, ok := val.(map[string]any); ok {
		if _, hasOp := m["operator"]; hasOp {
			return buildOperatorClause(key, m)
		}
	}

	switch v := val.(type) {
	case []any:
		if key == "id_categorie" && source == "devis" {
			vals := make([]string, 0, len(v))
			for _, item := range v {
				vals = append(vals, fmt.Sprintf("%v", item))
			}
			return fmt.Sprintf("%s in [%s]", key, strings.Join(vals, ", "))
		}

		quoted := make([]string, 0, len(v))
		for _, item := range v {
			s := fmt.Sprintf("%v", item)
			if key == "page_type" && strings.Contains(strings.ToLower(source), "siteweb") {
				normalized := strings.ReplaceAll(strings.ToLower(s), "-", "_")
				if pageTypeSiteweb[normalized] {
					quoted = append(quoted, fmt.Sprintf("'%s'", normalized))
				}
			} else {
				quoted = append(quoted, fmt.Sprintf("'%s'", s))
			}
		}
		return fmt.Sprintf("%s in [%s]", key, strings.Join(quoted, ", "))
	default:
		return fmt.Sprintf("%s == '%v'", key, val)
	}
}

func buildOperatorClause(key string, m map[string]any) string {
	op, _ := m["operator"].(string)
	values, _ := m["values"]

	if op == "entre" {
		if vm, ok := values.(map[string]any); ok {
			start, hasStart := vm["start"]
			end, hasEnd := vm["end"]
			if hasStart && hasEnd {
				return fmt.Sprintf("%s >= %v and %s <= %v", key, start, key, end)
			}
		}
	}

	if vm, ok := values.(map[string]any); ok {
		for _, v := range vm {
			return fmt.Sprintf("%s %s %v", key, op, v)
		}
	}
	return ""
}

func castNumericStr(val any, dtype string) string {
	if intTypes[dtype] {
		switch v := val.(type) {
		case float64:
			return fmt.Sprintf("%d", int64(v))
		default:
			return fmt.Sprintf("%v", v)
		}
	}
	return fmt.Sprintf("%v", val)
}

func strPtr(s string) *string {
	return &s
}
