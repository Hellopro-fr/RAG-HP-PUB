package tools

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/fieldmaskpb"

	"github.com/hellopro/mcp-normalize-unite/internal/mcp"
	unitregistrypb "github.com/hellopro/mcp-normalize-unite/proto/gen/unit_registry"
)

// registryTimeout bounds each unit-registry call: a write runs six guards and rebuilds
// a pint registry (about a second); a read is a single DB query.
const registryTimeout = 15 * time.Second

const sampleSchema = `{
		"type": "object",
		"description": "Exemple obligatoire, rejoué à chaque modification de l'unité (test de non-régression permanent).",
		"properties": {
			"label": {"type": "string", "description": "Libellé de caractéristique (ex. 'Poids')."},
			"value": {"type": ["string", "number"], "description": "Valeur brute (ex. 2)."},
			"unit": {"type": "string", "description": "Unité à normaliser ; par défaut le token de l'unité."},
			"data_type": {"type": "string", "enum": ["numeric", "numeric_range"], "description": "Défaut : 'numeric'."},
			"value_max": {"type": ["string", "number"], "description": "Borne haute, obligatoire si data_type = 'numeric_range'."},
			"expected_canonical_value": {"type": ["number", "string"], "description": "Valeur canonique attendue (ex. 50)."},
			"expected_canonical_max": {"type": ["number", "string"], "description": "Borne haute canonique attendue (numeric_range)."},
			"expected_canonical_unit": {"type": "string", "description": "Unité canonique attendue, telle que renvoyée par normalize_quantity (ex. 'kilogram')."}
		},
		"required": ["label", "value", "expected_canonical_value", "expected_canonical_unit"]
	}`

const createUnitDescription = "Créer une unité de normalisation dans le registre HelloPro (unit-registry-service). " +
	"Elle est active sur tous les réplicas du normaliseur en environ une seconde. Six garde-fous (G1–G6) valident " +
	"la définition pint, la dimension, les collisions de noms et rejouent l'exemple 'sample', obligatoire car il " +
	"devient un test permanent. Si un token désactivé existe déjà, il est réactivé avec les nouvelles valeurs."

const createUnitInputSchema = `{
	"type": "object",
	"properties": {
		"token": {"type": "string", "description": "Unité telle qu'elle apparaît dans les fiches (ex. 'sac', 'galettes'). Comparée en minuscules."},
		"dimension": {"type": "string", "description": "Dimension physique existante (ex. 'mass', 'length', 'volume', 'count'). Utiliser get_unit sur une unité proche pour voir le nom exact."},
		"pint_definition": {"type": "string", "description": "Définition pint si pint ne connaît pas l'unité : '<nom> = <expression> [= alias ...]' (ex. 'sac_ciment = 25 * kilogram'). À omettre si pint la connaît."},
		"aliases": {"type": "array", "items": {"type": "string"}, "description": "Autres graphies à reconnaître (ex. ['sacs'])."},
		"depends_on": {"type": "array", "items": {"type": "string"}, "description": "Unités personnalisées utilisées dans pint_definition."},
		"sample": ` + sampleSchema + `
	},
	"required": ["token", "dimension", "sample"]
}`

const updateUnitDescription = "Modifier une unité existante (par 'id' ou 'token'). Seuls les champs fournis changent ; " +
	"'aliases': [] vide la liste. Les six garde-fous sont rejoués : une unité issue du seed n'a pas d'exemple, " +
	"il faut donc fournir 'sample' pour la modifier. Effet sur tous les réplicas en environ une seconde."

const updateUnitInputSchema = `{
	"type": "object",
	"properties": {
		"id": {"type": "string", "description": "Identifiant de l'unité (ou utiliser 'token')."},
		"token": {"type": "string", "description": "Token exact de l'unité (ou utiliser 'id')."},
		"dimension": {"type": "string", "description": "Nouvelle dimension physique."},
		"pint_definition": {"type": "string", "description": "Nouvelle définition pint ; chaîne vide pour la retirer."},
		"aliases": {"type": "array", "items": {"type": "string"}, "description": "Remplace la liste des graphies ([] la vide)."},
		"depends_on": {"type": "array", "items": {"type": "string"}, "description": "Remplace la liste des dépendances."},
		"sample": ` + sampleSchema + `
	}
}`

const deactivateUnitDescription = "Désactiver une unité (par 'id' ou 'token') : elle n'est plus reconnue par le normaliseur " +
	"en environ une seconde. Refusé si d'autres unités en dépendent (le message les liste). Recréer le même token " +
	"avec create_unit la réactive."

const getUnitDescription = "Lire une unité du registre (par 'id' ou 'token') : définition pint, dimension, graphies, " +
	"statut, exemple de non-régression et types hérités de sa dimension (ex. DIMENSION, CAPACITY)."

const unitRefInputSchema = `{
	"type": "object",
	"properties": {
		"id": {"type": "string", "description": "Identifiant de l'unité."},
		"token": {"type": "string", "description": "Token exact de l'unité (sensible à la casse et aux accents)."}
	}
}`

type sampleView struct {
	Label                  string   `json:"label"`
	Unit                   string   `json:"unit,omitempty"`
	Value                  string   `json:"value"`
	ValueMax               *string  `json:"value_max,omitempty"`
	DataType               string   `json:"data_type"`
	ExpectedCanonicalValue float64  `json:"expected_canonical_value"`
	ExpectedCanonicalMax   *float64 `json:"expected_canonical_max,omitempty"`
	ExpectedCanonicalUnit  string   `json:"expected_canonical_unit"`
}

type unitView struct {
	ID              string      `json:"id"`
	Token           string      `json:"token"`
	Dimension       string      `json:"dimension,omitempty"`
	Types           []string    `json:"types"`
	PintDefinition  string      `json:"pint_definition,omitempty"`
	Aliases         []string    `json:"aliases"`
	DependsOn       []string    `json:"depends_on"`
	Status          string      `json:"status"`
	Source          string      `json:"source"`
	Sample          *sampleView `json:"sample,omitempty"`
	RegistryVersion int64       `json:"registry_version,omitempty"`
	CreatedBy       string      `json:"created_by,omitempty"`
	CreatedAt       string      `json:"created_at,omitempty"`
	UpdatedAt       string      `json:"updated_at,omitempty"`
}

func orEmpty(s []string) []string {
	if s == nil {
		return []string{}
	}
	return s
}

func toUnitView(u *unitregistrypb.UnitResponse) unitView {
	spec := u.GetSpec()
	view := unitView{
		ID: u.GetId(), Token: spec.GetToken(), Dimension: spec.GetDimension(), Types: orEmpty(u.GetTypes()),
		PintDefinition: spec.GetPintDefinition(), Aliases: orEmpty(spec.GetAliases()), DependsOn: orEmpty(spec.GetDependsOn()),
		Status: u.GetStatus(), Source: u.GetSource(), RegistryVersion: u.GetRegistryVersion(),
		CreatedBy: u.GetCreatedBy(), CreatedAt: u.GetCreatedAt(), UpdatedAt: u.GetUpdatedAt(),
	}
	if s := spec.GetRegressionSample(); s != nil {
		view.Sample = &sampleView{
			Label: s.GetLabel(), Unit: s.GetUnit(), Value: s.GetValue(), ValueMax: s.ValueMax, DataType: s.GetDataType(),
			ExpectedCanonicalValue: s.GetExpectedCanonicalValue(), ExpectedCanonicalMax: s.ExpectedCanonicalMax,
			ExpectedCanonicalUnit: s.GetExpectedCanonicalUnit(),
		}
	}
	return view
}

func registryCtx(ctx context.Context, clients *Clients, write bool) (context.Context, context.CancelFunc) {
	ctx, cancel := context.WithTimeout(ctx, registryTimeout)
	if write {
		ctx = metadata.AppendToOutgoingContext(ctx, "authorization", "Bearer "+clients.UnitsAdminKey)
	}
	return ctx, cancel
}

// registryError turns a unit-registry gRPC error into a tool error the agent can act on.
func registryError(op string, err error) *mcp.CallToolResult {
	if st, ok := status.FromError(err); ok {
		switch st.Code() {
		case codes.InvalidArgument, codes.AlreadyExists, codes.NotFound, codes.FailedPrecondition:
			return errorResult(st.Message())
		case codes.Unauthenticated:
			log.Printf("[tools] %s: unit registry rejected UNITS_ADMIN_KEY", op)
			return errorResult("unit registry rejected this MCP server's admin key (check UNITS_ADMIN_KEY)")
		}
	}
	log.Printf("[tools] %s failed: %v", op, err)
	return errorResult(fmt.Sprintf("unit registry unavailable: %v", err))
}

// stringList reads an optional array of non-empty strings; present reports whether the key was given.
func stringList(args map[string]any, key string) (list []string, present bool, errRes *mcp.CallToolResult) {
	raw, ok := args[key]
	if !ok || raw == nil {
		return nil, false, nil
	}
	items, ok := raw.([]any)
	if !ok {
		return nil, true, errorResult(fmt.Sprintf("'%s' must be an array of strings", key))
	}
	out := make([]string, 0, len(items))
	for _, item := range items {
		s, ok := item.(string)
		if !ok || strings.TrimSpace(s) == "" {
			return nil, true, errorResult(fmt.Sprintf("'%s' must contain non-empty strings", key))
		}
		out = append(out, strings.TrimSpace(s))
	}
	return out, true, nil
}

func prefixed(errRes *mcp.CallToolResult) *mcp.CallToolResult {
	return errorResult("sample: " + errRes.Content[0].Text)
}

// parseSample reads the optional 'sample' object; present reports whether the key was given.
func parseSample(args map[string]any) (*unitregistrypb.RegressionSample, bool, *mcp.CallToolResult) {
	raw, ok := args["sample"]
	if !ok || raw == nil {
		return nil, false, nil
	}
	obj, ok := raw.(map[string]any)
	if !ok {
		return nil, true, errorResult("'sample' must be an object")
	}
	label, errRes := requiredString(obj, "label")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	value, errRes := quantityValue(obj)
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	unit, errRes := optionalString(obj, "unit")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	dataType, errRes := optionalString(obj, "data_type")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	if dataType == "" {
		dataType = "numeric"
	}
	if !contains(allowedDataTypes, dataType) {
		return nil, true, errorResult(fmt.Sprintf("sample: 'data_type' must be one of %v", allowedDataTypes))
	}
	expected, errRes := optionalNumber(obj, "expected_canonical_value")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	if expected == nil {
		return nil, true, errorResult("sample: 'expected_canonical_value' parameter is required")
	}
	expectedUnit, errRes := requiredString(obj, "expected_canonical_unit")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	sample := &unitregistrypb.RegressionSample{
		Label: label, Unit: unit, Value: value, DataType: dataType,
		ExpectedCanonicalValue: *expected, ExpectedCanonicalUnit: expectedUnit,
	}
	valueMax, errRes := optionalNumber(obj, "value_max")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	if valueMax != nil {
		formatted := formatNumber(*valueMax)
		sample.ValueMax = &formatted
	}
	expectedMax, errRes := optionalNumber(obj, "expected_canonical_max")
	if errRes != nil {
		return nil, true, prefixed(errRes)
	}
	sample.ExpectedCanonicalMax = expectedMax
	if dataType == "numeric_range" && sample.ValueMax == nil {
		return nil, true, errorResult("sample: 'value_max' is required when data_type is 'numeric_range'")
	}
	return sample, true, nil
}

// resolveUnitID returns the id given directly, or looks the token up with an open read.
func resolveUnitID(ctx context.Context, clients *Clients, args map[string]any) (string, *mcp.CallToolResult) {
	id, errRes := optionalString(args, "id")
	if errRes != nil {
		return "", errRes
	}
	token, errRes := optionalString(args, "token")
	if errRes != nil {
		return "", errRes
	}
	switch {
	case id != "" && token != "":
		return "", errorResult("give either 'id' or 'token', not both")
	case id != "":
		return id, nil
	case token == "":
		return "", errorResult("'id' or 'token' is required")
	}
	callCtx, cancel := registryCtx(ctx, clients, false)
	defer cancel()
	unit, err := clients.Units.GetUnit(callCtx, &unitregistrypb.GetUnitRequest{Token: token})
	if err != nil {
		return "", registryError("get_unit", err)
	}
	return unit.GetId(), nil
}

func handleCreateUnit(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	token, errRes := requiredString(args, "token")
	if errRes != nil {
		return errRes, nil
	}
	dimension, errRes := requiredString(args, "dimension")
	if errRes != nil {
		return errRes, nil
	}
	definition, errRes := optionalString(args, "pint_definition")
	if errRes != nil {
		return errRes, nil
	}
	aliases, _, errRes := stringList(args, "aliases")
	if errRes != nil {
		return errRes, nil
	}
	dependsOn, _, errRes := stringList(args, "depends_on")
	if errRes != nil {
		return errRes, nil
	}
	sample, present, errRes := parseSample(args)
	if errRes != nil {
		return errRes, nil
	}
	if !present {
		return errorResult("'sample' parameter is required: it becomes the unit's permanent regression test"), nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	unit, err := clients.Units.RegisterUnit(callCtx, &unitregistrypb.RegisterUnitRequest{
		Spec: &unitregistrypb.UnitSpec{Token: token, Dimension: dimension, PintDefinition: definition,
			Aliases: aliases, DependsOn: dependsOn, RegressionSample: sample},
		CreatedBy: clients.Actor,
	})
	if err != nil {
		return registryError("create_unit", err), nil
	}
	return jsonResult(toUnitView(unit)), nil
}

func handleUpdateUnit(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	spec := &unitregistrypb.UnitSpec{}
	var paths []string
	if raw, ok := args["dimension"]; ok && raw != nil {
		dimension, errRes := requiredString(args, "dimension")
		if errRes != nil {
			return errRes, nil
		}
		spec.Dimension = dimension
		paths = append(paths, "dimension")
	}
	if _, ok := args["pint_definition"]; ok {
		definition, errRes := optionalString(args, "pint_definition")
		if errRes != nil {
			return errRes, nil
		}
		spec.PintDefinition = definition // "" clears it
		paths = append(paths, "pint_definition")
	}
	aliases, present, errRes := stringList(args, "aliases")
	if errRes != nil {
		return errRes, nil
	}
	if present {
		spec.Aliases = aliases
		paths = append(paths, "aliases")
	}
	dependsOn, present, errRes := stringList(args, "depends_on")
	if errRes != nil {
		return errRes, nil
	}
	if present {
		spec.DependsOn = dependsOn
		paths = append(paths, "depends_on")
	}
	sample, present, errRes := parseSample(args)
	if errRes != nil {
		return errRes, nil
	}
	if present {
		spec.RegressionSample = sample
		paths = append(paths, "regression_sample")
	}
	if len(paths) == 0 {
		return errorResult("nothing to update: give at least one of dimension, pint_definition, aliases, depends_on, sample"), nil
	}
	id, errRes := resolveUnitID(ctx, clients, args)
	if errRes != nil {
		return errRes, nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	unit, err := clients.Units.UpdateUnit(callCtx, &unitregistrypb.UpdateUnitRequest{
		Id: id, Spec: spec, UpdateMask: &fieldmaskpb.FieldMask{Paths: paths}, UpdatedBy: clients.Actor,
	})
	if err != nil {
		return registryError("update_unit", err), nil
	}
	return jsonResult(toUnitView(unit)), nil
}

func handleDeactivateUnit(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	id, errRes := resolveUnitID(ctx, clients, args)
	if errRes != nil {
		return errRes, nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	if _, err := clients.Units.DeleteUnit(callCtx, &unitregistrypb.DeleteUnitRequest{Id: id, DeletedBy: clients.Actor}); err != nil {
		return registryError("deactivate_unit", err), nil
	}
	return jsonResult(map[string]string{"id": id, "status": "DISABLED"}), nil
}

func handleGetUnit(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	id, errRes := optionalString(args, "id")
	if errRes != nil {
		return errRes, nil
	}
	token, errRes := optionalString(args, "token")
	if errRes != nil {
		return errRes, nil
	}
	if (id == "") == (token == "") {
		return errorResult("give exactly one of 'id' or 'token'"), nil
	}
	callCtx, cancel := registryCtx(ctx, clients, false)
	defer cancel()
	unit, err := clients.Units.GetUnit(callCtx, &unitregistrypb.GetUnitRequest{Id: id, Token: token})
	if err != nil {
		return registryError("get_unit", err), nil
	}
	return jsonResult(toUnitView(unit)), nil
}
