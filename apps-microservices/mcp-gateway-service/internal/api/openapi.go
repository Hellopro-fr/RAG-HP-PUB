package api

import (
	"encoding/json"
	"net/http"
)

// OpenAPISpec returns the static OpenAPI 3.0 specification for the MCP Gateway REST API.
func (h *Handler) OpenAPISpec() map[string]interface{} {
	return map[string]interface{}{
		"openapi": "3.0.3",
		"info": map[string]interface{}{
			"title":       "MCP Gateway Service",
			"description": "REST API pour la gestion dynamique des serveurs MCP (Model Context Protocol). Permet d'ajouter, lister, modifier, supprimer et surveiller les serveurs MCP backend en temps réel.",
			"version":     "1.0.0",
		},
		"paths": map[string]interface{}{
			"/api/v1/servers": map[string]interface{}{
				"get": map[string]interface{}{
					"summary":     "Lister les serveurs MCP",
					"description": "Retourne la liste de tous les serveurs MCP enregistrés avec filtres optionnels.",
					"operationId": "list_servers",
					"tags":        []string{"Servers"},
					"parameters": []map[string]interface{}{
						{
							"name": "is_active", "in": "query", "required": false,
							"schema":      map[string]string{"type": "string", "enum": "true,false"},
							"description": "Filtrer par statut actif/inactif",
						},
						{
							"name": "tag", "in": "query", "required": false,
							"schema":      map[string]string{"type": "string"},
							"description": "Filtrer par tag",
						},
					},
					"responses": map[string]interface{}{
						"200": map[string]interface{}{
							"description": "Liste des serveurs",
							"content": map[string]interface{}{
								"application/json": map[string]interface{}{
									"schema": map[string]interface{}{"$ref": "#/components/schemas/ListServersResponse"},
								},
							},
						},
					},
				},
				"post": map[string]interface{}{
					"summary":     "Ajouter un serveur MCP",
					"description": "Enregistre un nouveau serveur MCP backend. Si auto_discover est true, le gateway se connecte immédiatement pour découvrir les outils, ressources et prompts disponibles.",
					"operationId": "create_server",
					"tags":        []string{"Servers"},
					"requestBody": map[string]interface{}{
						"required": true,
						"content": map[string]interface{}{
							"application/json": map[string]interface{}{
								"schema": map[string]interface{}{"$ref": "#/components/schemas/CreateServerRequest"},
							},
						},
					},
					"responses": map[string]interface{}{
						"201": map[string]interface{}{
							"description": "Serveur créé",
							"content": map[string]interface{}{
								"application/json": map[string]interface{}{
									"schema": map[string]interface{}{"$ref": "#/components/schemas/ServerResponse"},
								},
							},
						},
						"400": map[string]interface{}{"description": "Requête invalide"},
						"409": map[string]interface{}{"description": "URL déjà enregistrée"},
					},
				},
			},
			"/api/v1/servers/{id}": map[string]interface{}{
				"get": map[string]interface{}{
					"summary":     "Détails d'un serveur",
					"description": "Retourne les détails complets d'un serveur MCP, incluant les outils, ressources et prompts découverts.",
					"operationId": "get_server",
					"tags":        []string{"Servers"},
					"parameters":  []map[string]interface{}{serverIDParam()},
					"responses": map[string]interface{}{
						"200": map[string]interface{}{
							"description": "Détails du serveur",
							"content": map[string]interface{}{
								"application/json": map[string]interface{}{
									"schema": map[string]interface{}{"$ref": "#/components/schemas/ServerDetailResponse"},
								},
							},
						},
						"404": map[string]interface{}{"description": "Serveur non trouvé"},
					},
				},
				"put": map[string]interface{}{
					"summary":     "Modifier un serveur",
					"description": "Met à jour la configuration d'un serveur MCP. Si l'URL change, une re-découverte automatique est lancée.",
					"operationId": "update_server",
					"tags":        []string{"Servers"},
					"parameters":  []map[string]interface{}{serverIDParam()},
					"requestBody": map[string]interface{}{
						"required": true,
						"content": map[string]interface{}{
							"application/json": map[string]interface{}{
								"schema": map[string]interface{}{"$ref": "#/components/schemas/UpdateServerRequest"},
							},
						},
					},
					"responses": map[string]interface{}{
						"200": map[string]interface{}{
							"description": "Serveur mis à jour",
							"content": map[string]interface{}{
								"application/json": map[string]interface{}{
									"schema": map[string]interface{}{"$ref": "#/components/schemas/ServerResponse"},
								},
							},
						},
						"404": map[string]interface{}{"description": "Serveur non trouvé"},
					},
				},
				"delete": map[string]interface{}{
					"summary":     "Supprimer un serveur",
					"description": "Supprime un serveur MCP et toutes ses capabilities associées (CASCADE).",
					"operationId": "delete_server",
					"tags":        []string{"Servers"},
					"parameters":  []map[string]interface{}{serverIDParam()},
					"responses": map[string]interface{}{
						"204": map[string]interface{}{"description": "Serveur supprimé"},
					},
				},
			},
			"/api/v1/servers/{id}/enable": map[string]interface{}{
				"post": map[string]interface{}{
					"summary":     "Activer un serveur",
					"description": "Active un serveur désactivé et lance une découverte pour l'enregistrer en mémoire.",
					"operationId": "enable_server",
					"tags":        []string{"Servers"},
					"parameters":  []map[string]interface{}{serverIDParam()},
					"responses": map[string]interface{}{
						"200": map[string]interface{}{
							"description": "Serveur activé",
							"content": map[string]interface{}{
								"application/json": map[string]interface{}{
									"schema": map[string]interface{}{"$ref": "#/components/schemas/ServerResponse"},
								},
							},
						},
					},
				},
			},
			"/api/v1/servers/{id}/disable": map[string]interface{}{
				"post": map[string]interface{}{
					"summary":     "Désactiver un serveur",
					"description": "Désactive un serveur sans le supprimer. Le serveur est retiré du registre en mémoire mais conservé en base.",
					"operationId": "disable_server",
					"tags":        []string{"Servers"},
					"parameters":  []map[string]interface{}{serverIDParam()},
					"responses": map[string]interface{}{
						"200": map[string]interface{}{
							"description": "Serveur désactivé",
							"content": map[string]interface{}{
								"application/json": map[string]interface{}{
									"schema": map[string]interface{}{"$ref": "#/components/schemas/ServerResponse"},
								},
							},
						},
					},
				},
			},
			"/api/v1/servers/{id}/discover": map[string]interface{}{
				"post": map[string]interface{}{
					"summary":     "Re-découvrir un serveur",
					"description": "Force une re-connexion et re-découverte des capabilities (outils, ressources, prompts) d'un serveur.",
					"operationId": "discover_server",
					"tags":        []string{"Servers"},
					"parameters":  []map[string]interface{}{serverIDParam()},
					"responses": map[string]interface{}{
						"200": map[string]interface{}{
							"description": "Serveur re-découvert avec ses capabilities",
							"content": map[string]interface{}{
								"application/json": map[string]interface{}{
									"schema": map[string]interface{}{"$ref": "#/components/schemas/ServerDetailResponse"},
								},
							},
						},
						"502": map[string]interface{}{"description": "Échec de la découverte"},
					},
				},
			},
			"/api/v1/servers/import": map[string]interface{}{
				"post": map[string]interface{}{
					"summary":     "Importer un fichier .mcp.json",
					"description": "Parse un fichier .mcp.json (tous formats supportés : standard, Claude Desktop, Cursor, Cline, Windsurf, mcp-remote wrapper, supergateway, stdio) et crée les serveurs correspondants. Les serveurs existants (même nom ou URL) sont ignorés.",
					"operationId": "import_mcp_json",
					"tags":        []string{"Import"},
					"parameters": []map[string]interface{}{
						{
							"name": "auto_discover", "in": "query", "required": false,
							"schema":      map[string]interface{}{"type": "string", "default": "true"},
							"description": "Si false, ne pas lancer la découverte automatique après import",
						},
					},
					"requestBody": map[string]interface{}{
						"required":    true,
						"description": "Contenu du fichier .mcp.json (tous formats acceptés)",
						"content": map[string]interface{}{
							"application/json": map[string]interface{}{
								"schema": map[string]interface{}{
									"type": "object",
									"example": map[string]interface{}{
										"mcpServers": map[string]interface{}{
											"my-server": map[string]interface{}{
												"url": "http://host:8000/mcp",
											},
											"my-stdio-server": map[string]interface{}{
												"command": "npx",
												"args":    []string{"-y", "@mcp/server"},
												"env":     map[string]string{"KEY": "val"},
											},
											"my-remote-wrapper": map[string]interface{}{
												"command": "npx",
												"args":    []string{"-y", "mcp-remote", "http://host:8000/sse", "--allow-http"},
											},
										},
									},
								},
							},
						},
					},
					"responses": map[string]interface{}{
						"200": map[string]interface{}{
							"description": "Résultat de l'import",
							"content": map[string]interface{}{
								"application/json": map[string]interface{}{
									"schema": map[string]interface{}{"$ref": "#/components/schemas/ImportResponse"},
								},
							},
						},
						"400": map[string]interface{}{"description": "JSON invalide ou aucun serveur trouvé"},
					},
				},
			},
			"/api/v1/servers/discover-all": map[string]interface{}{
				"post": map[string]interface{}{
					"summary":     "Re-découvrir tous les serveurs",
					"description": "Lance une re-découverte de tous les serveurs actifs.",
					"operationId": "discover_all_servers",
					"tags":        []string{"Servers"},
					"responses": map[string]interface{}{
						"200": map[string]interface{}{
							"description": "Résultats de la re-découverte",
						},
					},
				},
			},
			"/api/v1/tools": map[string]interface{}{
				"get": map[string]interface{}{
					"summary":     "Lister tous les outils MCP",
					"description": "Retourne la liste agrégée de tous les outils disponibles sur tous les serveurs actifs.",
					"operationId": "list_all_tools",
					"tags":        []string{"Capabilities"},
					"responses": map[string]interface{}{
						"200": map[string]interface{}{"description": "Liste des outils"},
					},
				},
			},
			"/api/v1/resources": map[string]interface{}{
				"get": map[string]interface{}{
					"summary":     "Lister toutes les ressources MCP",
					"description": "Retourne la liste agrégée de toutes les ressources disponibles sur tous les serveurs actifs.",
					"operationId": "list_all_resources",
					"tags":        []string{"Capabilities"},
					"responses": map[string]interface{}{
						"200": map[string]interface{}{"description": "Liste des ressources"},
					},
				},
			},
			"/api/v1/prompts": map[string]interface{}{
				"get": map[string]interface{}{
					"summary":     "Lister tous les prompts MCP",
					"description": "Retourne la liste agrégée de tous les prompts disponibles sur tous les serveurs actifs.",
					"operationId": "list_all_prompts",
					"tags":        []string{"Capabilities"},
					"responses": map[string]interface{}{
						"200": map[string]interface{}{"description": "Liste des prompts"},
					},
				},
			},
		},
		"components": map[string]interface{}{
			"schemas": map[string]interface{}{
				"CreateServerRequest": map[string]interface{}{
					"type":     "object",
					"required": []string{"name", "url"},
					"properties": map[string]interface{}{
						"name":                 map[string]interface{}{"type": "string", "description": "Nom humain du serveur", "example": "neo4j-cypher"},
						"url":                  map[string]interface{}{"type": "string", "description": "URL de base du serveur MCP", "example": "http://mcp-neo4j-cypher:8000"},
						"auth_headers":         map[string]interface{}{"type": "object", "additionalProperties": map[string]string{"type": "string"}, "description": "Headers d'authentification (chiffrés en base)"},
						"transport_preference": map[string]interface{}{"type": "string", "enum": []string{"auto", "sse", "streamable-http"}, "default": "auto"},
						"connect_timeout_ms":   map[string]interface{}{"type": "integer", "default": 10000},
						"tags":                 map[string]interface{}{"type": "array", "items": map[string]string{"type": "string"}, "example": []string{"neo4j", "database"}},
						"auto_discover":        map[string]interface{}{"type": "boolean", "default": false, "description": "Si true, découvrir les capabilities immédiatement"},
					},
				},
				"UpdateServerRequest": map[string]interface{}{
					"type": "object",
					"properties": map[string]interface{}{
						"name":                 map[string]interface{}{"type": "string"},
						"url":                  map[string]interface{}{"type": "string"},
						"auth_headers":         map[string]interface{}{"type": "object", "additionalProperties": map[string]string{"type": "string"}},
						"transport_preference": map[string]interface{}{"type": "string", "enum": []string{"auto", "sse", "streamable-http"}},
						"connect_timeout_ms":   map[string]interface{}{"type": "integer"},
						"tags":                 map[string]interface{}{"type": "array", "items": map[string]string{"type": "string"}},
					},
				},
				"ServerResponse": map[string]interface{}{
					"type": "object",
					"properties": map[string]interface{}{
						"id":                   map[string]interface{}{"type": "string", "format": "uuid"},
						"name":                 map[string]interface{}{"type": "string"},
						"url":                  map[string]interface{}{"type": "string"},
						"message_url":          map[string]interface{}{"type": "string"},
						"transport_type":       map[string]interface{}{"type": "string"},
						"server_name":          map[string]interface{}{"type": "string"},
						"server_version":       map[string]interface{}{"type": "string"},
						"transport_preference": map[string]interface{}{"type": "string"},
						"connect_timeout_ms":   map[string]interface{}{"type": "integer"},
						"is_active":            map[string]interface{}{"type": "boolean"},
						"health_status":        map[string]interface{}{"type": "string", "enum": []string{"unknown", "healthy", "degraded", "unhealthy"}},
						"last_health_check":    map[string]interface{}{"type": "string", "format": "date-time"},
						"last_error":           map[string]interface{}{"type": "string"},
						"last_discovered_at":   map[string]interface{}{"type": "string", "format": "date-time"},
						"tools_count":          map[string]interface{}{"type": "integer"},
						"resources_count":      map[string]interface{}{"type": "integer"},
						"prompts_count":        map[string]interface{}{"type": "integer"},
						"tags":                 map[string]interface{}{"type": "array", "items": map[string]string{"type": "string"}},
						"created_at":           map[string]interface{}{"type": "string", "format": "date-time"},
						"updated_at":           map[string]interface{}{"type": "string", "format": "date-time"},
					},
				},
				"ServerDetailResponse": map[string]interface{}{
					"allOf": []map[string]interface{}{
						{"$ref": "#/components/schemas/ServerResponse"},
						{
							"type": "object",
							"properties": map[string]interface{}{
								"tools":     map[string]interface{}{"type": "array", "items": map[string]interface{}{"$ref": "#/components/schemas/ToolResponse"}},
								"resources": map[string]interface{}{"type": "array", "items": map[string]interface{}{"$ref": "#/components/schemas/ResourceResponse"}},
								"prompts":   map[string]interface{}{"type": "array", "items": map[string]interface{}{"$ref": "#/components/schemas/PromptResponse"}},
							},
						},
					},
				},
				"ToolResponse": map[string]interface{}{
					"type": "object",
					"properties": map[string]interface{}{
						"name":         map[string]interface{}{"type": "string"},
						"description":  map[string]interface{}{"type": "string"},
						"input_schema": map[string]interface{}{"type": "object"},
					},
				},
				"ResourceResponse": map[string]interface{}{
					"type": "object",
					"properties": map[string]interface{}{
						"uri":         map[string]interface{}{"type": "string"},
						"name":        map[string]interface{}{"type": "string"},
						"description": map[string]interface{}{"type": "string"},
						"mime_type":   map[string]interface{}{"type": "string"},
					},
				},
				"PromptResponse": map[string]interface{}{
					"type": "object",
					"properties": map[string]interface{}{
						"name":        map[string]interface{}{"type": "string"},
						"description": map[string]interface{}{"type": "string"},
						"arguments": map[string]interface{}{
							"type": "array",
							"items": map[string]interface{}{
								"type": "object",
								"properties": map[string]interface{}{
									"name":        map[string]interface{}{"type": "string"},
									"description": map[string]interface{}{"type": "string"},
									"is_required": map[string]interface{}{"type": "boolean"},
								},
							},
						},
					},
				},
				"ListServersResponse": map[string]interface{}{
					"type": "object",
					"properties": map[string]interface{}{
						"servers": map[string]interface{}{"type": "array", "items": map[string]interface{}{"$ref": "#/components/schemas/ServerResponse"}},
						"total":   map[string]interface{}{"type": "integer"},
					},
				},
				"ImportResponse": map[string]interface{}{
					"type": "object",
					"properties": map[string]interface{}{
						"imported": map[string]interface{}{"type": "integer", "description": "Nombre de serveurs créés"},
						"skipped":  map[string]interface{}{"type": "integer", "description": "Nombre de serveurs ignorés (déjà existants)"},
						"errors":   map[string]interface{}{"type": "integer", "description": "Nombre d'erreurs"},
						"results": map[string]interface{}{
							"type": "array",
							"items": map[string]interface{}{
								"type": "object",
								"properties": map[string]interface{}{
									"name":   map[string]interface{}{"type": "string"},
									"id":     map[string]interface{}{"type": "string", "format": "uuid"},
									"status": map[string]interface{}{"type": "string", "enum": []string{"created", "skipped", "error"}},
									"error":  map[string]interface{}{"type": "string"},
								},
							},
						},
					},
				},
				"ErrorResponse": map[string]interface{}{
					"type": "object",
					"properties": map[string]interface{}{
						"error": map[string]interface{}{"type": "string"},
					},
				},
			},
		},
	}
}

func serverIDParam() map[string]interface{} {
	return map[string]interface{}{
		"name": "id", "in": "path", "required": true,
		"schema":      map[string]string{"type": "string", "format": "uuid"},
		"description": "UUID du serveur MCP",
	}
}

// handleOpenAPI serves the OpenAPI 3.0 JSON specification.
func (h *Handler) handleOpenAPI(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(h.OpenAPISpec())
}
