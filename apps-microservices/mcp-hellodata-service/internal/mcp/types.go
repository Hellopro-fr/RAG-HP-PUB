package mcp

import "encoding/json"

const (
	CodeErreurParsing   = -32700
	CodeRequeteInvalide = -32600
	CodeMethodeInconnue = -32601
	CodeParamsInvalides = -32602
	CodeErreurInterne   = -32603
)

type Requete struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Methode string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

type ErreurRPC struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type Reponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Result  interface{}     `json:"result,omitempty"`
	Error   *ErreurRPC      `json:"error,omitempty"`
}

type Outil struct {
	Nom         string      `json:"name"`
	Description string      `json:"description"`
	SchemaEntre interface{} `json:"inputSchema"`
}

func OK(id json.RawMessage, result interface{}) Reponse {
	return Reponse{JSONRPC: "2.0", ID: id, Result: result}
}

func Echec(id json.RawMessage, code int, message string) Reponse {
	return Reponse{JSONRPC: "2.0", ID: id, Error: &ErreurRPC{Code: code, Message: message}}
}
