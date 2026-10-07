package tools

import (
	"context"
	"sort"

	"google.golang.org/protobuf/types/known/fieldmaskpb"

	"github.com/hellopro/mcp-normalize-unite/internal/mcp"
	unitregistrypb "github.com/hellopro/mcp-normalize-unite/proto/gen/unit_registry"
)

const createUnitTypeDescription = "Créer un type d'unité (catégorie métier, ex. DIMENSION, CAPACITY). Appeler d'abord " +
	"get_unit_type sans argument pour réutiliser un type existant : un code trop proche d'un type existant est refusé. " +
	"Code en MAJUSCULES (lettres, chiffres, _), immuable. Recréer un code désactivé le réactive. Un type ne change pas la normalisation."

const createUnitTypeInputSchema = `{
	"type": "object",
	"properties": {
		"code": {"type": "string", "description": "Code stable en MAJUSCULES, ex. 'CAPACITY'."},
		"label": {"type": "string", "description": "Libellé affiché, ex. 'Capacité'."},
		"description": {"type": "string", "description": "Description facultative."}
	},
	"required": ["code", "label"]
}`

const updateUnitTypeDescription = "Modifier le libellé ou la description d'un type d'unité (par 'id' ou 'code'). Le code est immuable."

const updateUnitTypeInputSchema = `{
	"type": "object",
	"properties": {
		"id": {"type": "string"},
		"code": {"type": "string", "description": "Code du type à modifier (ou utiliser 'id')."},
		"label": {"type": "string"},
		"description": {"type": "string"}
	}
}`

const deactivateUnitTypeDescription = "Désactiver un type d'unité (par 'id' ou 'code') : il n'apparaît plus sur les unités, " +
	"mais ses liens aux dimensions sont conservés et reviennent si on le recrée avec create_unit_type."

const getUnitTypeDescription = "Lire un type d'unité (par 'id' ou 'code') avec les dimensions qui lui sont liées, " +
	"ou, sans argument, lister tous les types actifs."

const unitTypeRefInputSchema = `{
	"type": "object",
	"properties": {
		"id": {"type": "string"},
		"code": {"type": "string", "description": "Code du type, ex. 'CAPACITY'."}
	}
}`

const setDimensionTypesDescription = "Définir les types d'une dimension physique (ex. 'length' -> ['DIMENSION']). " +
	"Remplace l'ensemble existant ; [] le vide. Toutes les unités de cette dimension héritent de ces types. " +
	"Chaque code doit exister et être actif (créer les nouveaux avec create_unit_type)."

const setDimensionTypesInputSchema = `{
	"type": "object",
	"properties": {
		"dimension": {"type": "string", "description": "Nom exact de la dimension (ex. 'length', 'volume', 'mass')."},
		"type_codes": {"type": "array", "items": {"type": "string"}, "description": "Codes de types, ex. ['CAPACITY']."}
	},
	"required": ["dimension", "type_codes"]
}`

type unitTypeView struct {
	ID          string   `json:"id"`
	Code        string   `json:"code"`
	Label       string   `json:"label"`
	Description string   `json:"description,omitempty"`
	IsActive    bool     `json:"is_active"`
	Dimensions  []string `json:"dimensions"`
	CreatedBy   string   `json:"created_by,omitempty"`
	CreatedAt   string   `json:"created_at,omitempty"`
	UpdatedAt   string   `json:"updated_at,omitempty"`
}

func toUnitTypeView(t *unitregistrypb.UnitTypeResponse) unitTypeView {
	return unitTypeView{
		ID: t.GetId(), Code: t.GetSpec().GetCode(), Label: t.GetSpec().GetLabel(), Description: t.GetSpec().GetDescription(),
		IsActive: t.GetIsActive(), Dimensions: orEmpty(t.GetDimensions()),
		CreatedBy: t.GetCreatedBy(), CreatedAt: t.GetCreatedAt(), UpdatedAt: t.GetUpdatedAt(),
	}
}

// resolveTypeID returns the id given directly, or looks the code up with an open read.
func resolveTypeID(ctx context.Context, clients *Clients, args map[string]any) (string, *mcp.CallToolResult) {
	id, errRes := optionalString(args, "id")
	if errRes != nil {
		return "", errRes
	}
	code, errRes := optionalString(args, "code")
	if errRes != nil {
		return "", errRes
	}
	switch {
	case id != "" && code != "":
		return "", errorResult("give either 'id' or 'code', not both")
	case id != "":
		return id, nil
	case code == "":
		return "", errorResult("'id' or 'code' is required")
	}
	callCtx, cancel := registryCtx(ctx, clients, false)
	defer cancel()
	found, err := clients.Units.GetUnitType(callCtx, &unitregistrypb.GetUnitTypeRequest{Code: code})
	if err != nil {
		return "", registryError("get_unit_type", err)
	}
	return found.GetId(), nil
}

func handleCreateUnitType(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	code, errRes := requiredString(args, "code")
	if errRes != nil {
		return errRes, nil
	}
	label, errRes := requiredString(args, "label")
	if errRes != nil {
		return errRes, nil
	}
	description, errRes := optionalString(args, "description")
	if errRes != nil {
		return errRes, nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	created, err := clients.Units.CreateUnitType(callCtx, &unitregistrypb.CreateUnitTypeRequest{
		Spec: &unitregistrypb.UnitTypeSpec{Code: code, Label: label, Description: description}, CreatedBy: clients.Actor,
	})
	if err != nil {
		return registryError("create_unit_type", err), nil
	}
	return jsonResult(toUnitTypeView(created)), nil
}

func handleUpdateUnitType(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	spec := &unitregistrypb.UnitTypeSpec{}
	var paths []string
	if raw, ok := args["label"]; ok && raw != nil {
		label, errRes := requiredString(args, "label")
		if errRes != nil {
			return errRes, nil
		}
		spec.Label = label
		paths = append(paths, "label")
	}
	if _, ok := args["description"]; ok {
		description, errRes := optionalString(args, "description")
		if errRes != nil {
			return errRes, nil
		}
		spec.Description = description
		paths = append(paths, "description")
	}
	if len(paths) == 0 {
		return errorResult("nothing to update: give 'label' and/or 'description'"), nil
	}
	id, errRes := resolveTypeID(ctx, clients, args)
	if errRes != nil {
		return errRes, nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	updated, err := clients.Units.UpdateUnitType(callCtx, &unitregistrypb.UpdateUnitTypeRequest{
		Id: id, Spec: spec, UpdateMask: &fieldmaskpb.FieldMask{Paths: paths}, UpdatedBy: clients.Actor,
	})
	if err != nil {
		return registryError("update_unit_type", err), nil
	}
	return jsonResult(toUnitTypeView(updated)), nil
}

func handleDeactivateUnitType(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	id, errRes := resolveTypeID(ctx, clients, args)
	if errRes != nil {
		return errRes, nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	deactivated, err := clients.Units.DeactivateUnitType(callCtx, &unitregistrypb.DeactivateUnitTypeRequest{Id: id, UpdatedBy: clients.Actor})
	if err != nil {
		return registryError("deactivate_unit_type", err), nil
	}
	return jsonResult(toUnitTypeView(deactivated)), nil
}

func handleGetUnitType(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	id, errRes := optionalString(args, "id")
	if errRes != nil {
		return errRes, nil
	}
	code, errRes := optionalString(args, "code")
	if errRes != nil {
		return errRes, nil
	}
	callCtx, cancel := registryCtx(ctx, clients, false)
	defer cancel()
	if id == "" && code == "" {
		listed, err := clients.Units.ListUnitTypes(callCtx, &unitregistrypb.ListUnitTypesRequest{})
		if err != nil {
			return registryError("get_unit_type", err), nil
		}
		views := make([]unitTypeView, 0, len(listed.GetTypes()))
		for _, t := range listed.GetTypes() {
			views = append(views, toUnitTypeView(t))
		}
		sort.Slice(views, func(i, j int) bool { return views[i].Code < views[j].Code })
		return jsonResult(views), nil
	}
	if id != "" && code != "" {
		return errorResult("give either 'id' or 'code', not both"), nil
	}
	found, err := clients.Units.GetUnitType(callCtx, &unitregistrypb.GetUnitTypeRequest{Id: id, Code: code})
	if err != nil {
		return registryError("get_unit_type", err), nil
	}
	return jsonResult(toUnitTypeView(found)), nil
}

func handleSetDimensionTypes(ctx context.Context, clients *Clients, args map[string]any) (*mcp.CallToolResult, error) {
	dimension, errRes := requiredString(args, "dimension")
	if errRes != nil {
		return errRes, nil
	}
	codes, present, errRes := stringList(args, "type_codes")
	if errRes != nil {
		return errRes, nil
	}
	if !present {
		return errorResult("'type_codes' parameter is required ([] clears the dimension's types)"), nil
	}
	callCtx, cancel := registryCtx(ctx, clients, true)
	defer cancel()
	result, err := clients.Units.SetDimensionTypes(callCtx, &unitregistrypb.SetDimensionTypesRequest{
		Dimension: dimension, TypeCodes: codes, UpdatedBy: clients.Actor,
	})
	if err != nil {
		return registryError("set_dimension_types", err), nil
	}
	return jsonResult(map[string]any{"dimension": result.GetDimension(), "type_codes": orEmpty(result.GetTypeCodes())}), nil
}
