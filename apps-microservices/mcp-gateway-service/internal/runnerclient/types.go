package runnerclient

// SpawnRequest is sent to POST /admin/instances.
// WARNING: CredentialsJSON contains the plaintext SA JSON private key.
// Callers must NOT log the full SpawnRequest (use structured logging with
// explicit field selection, or redact CredentialsJSON before logging).
type SpawnRequest struct {
	InstanceID      string            `json:"instance_id"`
	TemplateSlug    string            `json:"template_slug"`
	StdioCommand    string            `json:"stdio_command"`
	StdioArgs       []string          `json:"stdio_args"`
	Env             map[string]string `json:"env"`
	CredentialsJSON string            `json:"credentials_json"` // raw SA JSON
	CredentialsHash string            `json:"credentials_hash"` // sha256 hex
	// RunnerPort, when non-nil, is the last-known port the runner used for
	// this instance. The runner tries to re-allocate the same port so the
	// gateway's stored mcp_servers.url stays valid across runner restarts.
	// Nil for fresh POST /admin/instances calls.
	RunnerPort *int `json:"runner_port,omitempty"`
}

type SpawnResponse struct {
	Port int `json:"port"`
	PID  int `json:"pid"`
}

type InstanceStatus struct {
	ID         string `json:"id"`
	Port       int    `json:"port"`
	PID        int    `json:"pid"`
	Status     string `json:"status"` // pending | running | failed | stopped
	UptimeSec  int    `json:"uptime_s"`
	LastError  string `json:"last_error,omitempty"`
	StderrTail string `json:"stderr_tail,omitempty"`
}

type ReconcileRequest struct {
	DesiredInstances []SpawnRequest `json:"desired_instances"`
}
