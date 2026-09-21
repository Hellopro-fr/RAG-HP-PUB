package config

import (
	"os"
	"testing"
)

func poser(t *testing.T, kv map[string]string) {
	t.Helper()
	for _, k := range []string{"HELLODATA_BASE_URL", "HELLODATA_TOKEN", "HELLODATA_ALLOWED_EMAILS", "HELLODATA_PUBLIC_URL", "MCP_PORT"} {
		os.Unsetenv(k)
	}
	for k, v := range kv {
		os.Setenv(k, v)
	}
}

func TestCharger_ValeursParDefaut(t *testing.T) {
	poser(t, map[string]string{
		"HELLODATA_BASE_URL": "https://bo.example.test/admin/mcp/hellodata",
		"HELLODATA_TOKEN":    "jeton",
	})
	c, err := Charger()
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	if c.Port != 8597 {
		t.Errorf("Port = %d, attendu 8597", c.Port)
	}
	if c.EmailsAutorises != "" {
		t.Errorf("EmailsAutorises = %q, attendu vide", c.EmailsAutorises)
	}
}

// Une URL ou un jeton manquant doit empecher le demarrage. Un service qui
// demarre sans jeton ne peut rien faire et le decouvre au premier appel.
func TestCharger_RefuseUneConfigIncomplete(t *testing.T) {
	cas := []struct {
		nom string
		env map[string]string
	}{
		{"sans URL", map[string]string{"HELLODATA_TOKEN": "jeton"}},
		{"sans jeton", map[string]string{"HELLODATA_BASE_URL": "https://bo.example.test"}},
		{"les deux absents", map[string]string{}},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			poser(t, c.env)
			if _, err := Charger(); err == nil {
				t.Fatal("attendu une erreur, obtenu nil")
			}
		})
	}
}

func TestCharger_PortInvalide(t *testing.T) {
	poser(t, map[string]string{
		"HELLODATA_BASE_URL": "https://bo.example.test",
		"HELLODATA_TOKEN":    "jeton",
		"MCP_PORT":           "pas-un-nombre",
	})
	if _, err := Charger(); err == nil {
		t.Fatal("attendu une erreur sur un port illisible")
	}
}

func TestCharger_RetireLeSlashFinal(t *testing.T) {
	poser(t, map[string]string{
		"HELLODATA_BASE_URL": "https://bo.example.test/admin/mcp/hellodata/",
		"HELLODATA_TOKEN":    "jeton",
	})
	c, _ := Charger()
	if c.BaseURL != "https://bo.example.test/admin/mcp/hellodata" {
		t.Errorf("BaseURL = %q, slash final non retire", c.BaseURL)
	}
}
