package tools

import (
	"context"
	"fmt"
	"math"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/hellopro/mcp-normalize-unite/internal/mcp"
	normalizationpb "github.com/hellopro/mcp-normalize-unite/proto/gen/graph_normalization"
)

// rpcTimeout bounds each gRPC call; the backend is a pure in-memory pint conversion.
const rpcTimeout = 10 * time.Second

// The backend returns an empty result (success=false) for any other data_type,
// so an omitted data_type must default to "numeric" rather than "".
var allowedDataTypes = []string{"numeric", "numeric_range"}

const normalizeQuantityDescription = "Normaliser une quantité (valeur + unité) vers son unité canonique HelloPro " +
	"(ex. 2 t -> 2000 kg, 50 cm -> 0.5 m, 3 kW -> 3000 W). Le libellé de la caractéristique " +
	"(ex. 'Poids', 'Longueur', 'Puissance') sert à lever l'ambiguïté quand l'unité seule ne suffit pas " +
	"ou est absente. Utilise le service gRPC graph-rag-normalize-unite-service."

const normalizeQuantityInputSchema = `{
	"type": "object",
	"properties": {
		"label": {
			"type": "string",
			"description": "Libellé de la caractéristique (ex. 'Poids', 'Hauteur', 'Débit d'air'). Obligatoire : il détermine la dimension physique."
		},
		"value": {
			"type": ["string", "number"],
			"description": "Valeur brute (ex. 12.5, '12.5', '+/- 2'). Les préfixes de tolérance '+/-' et '±' sont acceptés."
		},
		"unit": {
			"type": "string",
			"description": "Unité source telle qu'extraite (ex. 'kg', 'mm', 'dB(A)', 'tr/min', 'm³/h'). Optionnelle : sans unité, la valeur est supposée déjà canonique."
		},
		"data_type": {
			"type": "string",
			"enum": ["numeric", "numeric_range"],
			"description": "Type de donnée de la caractéristique. Défaut : 'numeric'."
		}
	},
	"required": ["label", "value"]
}`

const normalizeRangeDescription = "Normaliser un intervalle numérique (min et/ou max + unité) vers l'unité canonique HelloPro " +
	"(ex. 10-50 cm -> 0.1-0.5 m). Chaque borne est normalisée indépendamment ; si une borne fournie " +
	"ne peut pas être normalisée, l'appel échoue en nommant la borne au lieu de renvoyer une valeur par défaut."

const normalizeRangeInputSchema = `{
	"type": "object",
	"properties": {
		"label": {
			"type": "string",
			"description": "Libellé de la caractéristique (ex. 'Température d'utilisation', 'Longueur'). Obligatoire."
		},
		"min_value": {
			"type": ["number", "string"],
			"description": "Borne basse de l'intervalle. Au moins une des deux bornes est requise."
		},
		"max_value": {
			"type": ["number", "string"],
			"description": "Borne haute de l'intervalle. Au moins une des deux bornes est requise."
		},
		"unit": {
			"type": "string",
			"description": "Unité source commune aux deux bornes (ex. 'cm', '°C', 'bar'). Optionnelle."
		}
	},
	"required": ["label"]
}`

type quantityResult struct {
	Label          string  `json:"label"`
	Value          string  `json:"value"`
	Unit           string  `json:"unit,omitempty"`
	CanonicalValue float64 `json:"canonical_value"`
	CanonicalUnit  string  `json:"canonical_unit"`
}

type rangeResult struct {
	Label         string   `json:"label"`
	Unit          string   `json:"unit,omitempty"`
	MinValue      *float64 `json:"min_value,omitempty"`
	MaxValue      *float64 `json:"max_value,omitempty"`
	CanonicalMin  *float64 `json:"canonical_min,omitempty"`
	CanonicalMax  *float64 `json:"canonical_max,omitempty"`
	CanonicalUnit string   `json:"canonical_unit"`
}

func handleNormalizeQuantity(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	label, errRes := requiredString(args, "label")
	if errRes != nil {
		return errRes, nil
	}

	value, errRes := quantityValue(args)
	if errRes != nil {
		return errRes, nil
	}

	unit, errRes := optionalString(args, "unit")
	if errRes != nil {
		return errRes, nil
	}

	dataType, errRes := optionalString(args, "data_type")
	if errRes != nil {
		return errRes, nil
	}
	if dataType == "" {
		dataType = "numeric"
	}
	if !contains(allowedDataTypes, dataType) {
		return errorResult(fmt.Sprintf("'data_type' must be one of %s", strings.Join(allowedDataTypes, ", "))), nil
	}

	resp, err := normalizeOne(ctx, clients, label, unit, value, dataType)
	if err != nil {
		return nil, err
	}
	if !resp.GetSuccess() {
		return errorResult(backendFailure(resp.GetErrorMessage(), label, value, unit)), nil
	}

	return jsonResult(quantityResult{
		Label:          label,
		Value:          value,
		Unit:           unit,
		CanonicalValue: resp.GetCanonicalValue(),
		CanonicalUnit:  resp.GetCanonicalUnit(),
	}), nil
}

// handleNormalizeRange normalizes each bound with its own NormalizeQuantity call
// instead of the NormalizeRange RPC. NormalizeRange silently drops a bound that
// fails to convert, and proto3 then reports it as 0.0 with success=true — a
// plausible-looking wrong number. Per-bound calls run the exact same backend
// logic (normalize_range is two normalize(..., "numeric") calls) and let us say
// which bound failed.
func handleNormalizeRange(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	label, errRes := requiredString(args, "label")
	if errRes != nil {
		return errRes, nil
	}

	unit, errRes := optionalString(args, "unit")
	if errRes != nil {
		return errRes, nil
	}

	minVal, errRes := optionalNumber(args, "min_value")
	if errRes != nil {
		return errRes, nil
	}
	maxVal, errRes := optionalNumber(args, "max_value")
	if errRes != nil {
		return errRes, nil
	}
	if minVal == nil && maxVal == nil {
		return errorResult("at least one of 'min_value' or 'max_value' is required"), nil
	}
	if minVal != nil && maxVal != nil && *minVal > *maxVal {
		return errorResult(fmt.Sprintf("'min_value' (%v) must not exceed 'max_value' (%v)", *minVal, *maxVal)), nil
	}

	type bound struct {
		name  string
		input *float64
		resp  *normalizationpb.NormalizeQuantityResponse
		err   error
	}
	bounds := []*bound{{name: "min_value", input: minVal}, {name: "max_value", input: maxVal}}

	var wg sync.WaitGroup
	for _, b := range bounds {
		if b.input == nil {
			continue
		}
		wg.Add(1)
		go func(b *bound) {
			defer wg.Done()
			b.resp, b.err = normalizeOne(ctx, clients, label, unit, formatNumber(*b.input), "numeric")
		}(b)
	}
	wg.Wait()

	result := rangeResult{Label: label, Unit: unit, MinValue: minVal, MaxValue: maxVal}
	for _, b := range bounds {
		if b.input == nil {
			continue
		}
		if b.err != nil {
			return nil, fmt.Errorf("%s: %w", b.name, b.err)
		}
		if !b.resp.GetSuccess() {
			return errorResult(fmt.Sprintf("%s: %s", b.name,
				backendFailure(b.resp.GetErrorMessage(), label, formatNumber(*b.input), unit))), nil
		}
		canonical := b.resp.GetCanonicalValue()
		if b.name == "min_value" {
			result.CanonicalMin = &canonical
		} else {
			result.CanonicalMax = &canonical
		}
		if result.CanonicalUnit == "" {
			result.CanonicalUnit = b.resp.GetCanonicalUnit()
		}
	}

	return jsonResult(result), nil
}

func normalizeOne(ctx context.Context, clients *Clients, label, unit, value, dataType string) (*normalizationpb.NormalizeQuantityResponse, error) {
	callCtx, cancel := context.WithTimeout(ctx, rpcTimeout)
	defer cancel()

	resp, err := clients.Normalization.NormalizeQuantity(callCtx, &normalizationpb.NormalizeQuantityRequest{
		Label:    label,
		Unit:     unit,
		Value:    value,
		DataType: dataType,
	})
	if err != nil {
		return nil, fmt.Errorf("NormalizeQuantity gRPC call failed: %w", err)
	}
	return resp, nil
}

// backendFailure keeps the backend's own message and echoes the input, because
// the backend's generic "Could not normalize value" omits the value and unit.
func backendFailure(msg, label, value, unit string) string {
	if msg == "" {
		msg = "normalization failed"
	}
	return fmt.Sprintf("%s (label=%q, value=%q, unit=%q). Vérifier que l'unité correspond au libellé.", msg, label, value, unit)
}

// -- Argument helpers ----------------------------------------------------------

func requiredString(args map[string]any, key string) (string, *mcp.CallToolResult) {
	raw, ok := args[key]
	if !ok || raw == nil {
		return "", errorResult(fmt.Sprintf("'%s' parameter is required", key))
	}
	s, ok := raw.(string)
	if !ok {
		return "", errorResult(fmt.Sprintf("'%s' must be a string", key))
	}
	s = strings.TrimSpace(s)
	if s == "" {
		return "", errorResult(fmt.Sprintf("'%s' must not be empty", key))
	}
	return s, nil
}

func optionalString(args map[string]any, key string) (string, *mcp.CallToolResult) {
	raw, ok := args[key]
	if !ok || raw == nil {
		return "", nil
	}
	s, ok := raw.(string)
	if !ok {
		return "", errorResult(fmt.Sprintf("'%s' must be a string", key))
	}
	return strings.TrimSpace(s), nil
}

// quantityValue accepts a JSON number or a raw string; the proto carries the
// value as a string so the backend can strip tolerance prefixes itself.
func quantityValue(args map[string]any) (string, *mcp.CallToolResult) {
	raw, ok := args["value"]
	if !ok || raw == nil {
		return "", errorResult("'value' parameter is required")
	}
	switch v := raw.(type) {
	case string:
		v = strings.TrimSpace(v)
		if v == "" {
			return "", errorResult("'value' must not be empty")
		}
		return v, nil
	case float64:
		if math.IsNaN(v) || math.IsInf(v, 0) {
			return "", errorResult("'value' must be a finite number")
		}
		return formatNumber(v), nil
	default:
		return "", errorResult("'value' must be a number or a string")
	}
}

func optionalNumber(args map[string]any, key string) (*float64, *mcp.CallToolResult) {
	raw, ok := args[key]
	if !ok || raw == nil {
		return nil, nil
	}
	var f float64
	switch v := raw.(type) {
	case float64:
		f = v
	case string:
		s := strings.TrimSpace(v)
		if s == "" {
			return nil, nil
		}
		parsed, err := strconv.ParseFloat(s, 64)
		if err != nil {
			return nil, errorResult(fmt.Sprintf("'%s' must be a number, got %q", key, v))
		}
		f = parsed
	default:
		return nil, errorResult(fmt.Sprintf("'%s' must be a number", key))
	}
	if math.IsNaN(f) || math.IsInf(f, 0) {
		return nil, errorResult(fmt.Sprintf("'%s' must be a finite number", key))
	}
	return &f, nil
}

func formatNumber(f float64) string {
	return strconv.FormatFloat(f, 'f', -1, 64)
}

func contains(list []string, s string) bool {
	for _, v := range list {
		if v == s {
			return true
		}
	}
	return false
}
