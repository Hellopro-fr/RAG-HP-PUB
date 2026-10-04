package config

import (
	"os"
	"testing"
)

func poser(t *testing.T, kv map[string]string) {
	t.Helper()
	for _, k := range []string{"HELLODATA_BASE_URL", "HELLODATA_TOKEN", "HELLODATA_PUBLIC_URL", "HELLODATA_WEBHOOK_URL", "HELLODATA_WEBHOOK_TOKEN", "MCP_PORT"} {
		os.Unsetenv(k)
	}
	for k, v := range kv {
		os.Setenv(k, v)
	}
}

// complete rend un environnement minimal valide ; les tests en retirent
// ou en modifient une entree.
func complete() map[string]string {
	return map[string]string{
		"HELLODATA_BASE_URL":      "https://bo.example.test/admin/mcp/hellodata",
		"HELLODATA_TOKEN":         "jeton",
		"HELLODATA_WEBHOOK_URL":   "https://front.example.test/partenaires_externes/mcp/hellodata",
		"HELLODATA_WEBHOOK_TOKEN": "jeton-webhook",
	}
}

func TestCharger_ValeursParDefaut(t *testing.T) {
	poser(t, complete())
	c, err := Charger()
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	if c.Port != 8597 {
		t.Errorf("Port = %d, attendu 8597", c.Port)
	}
}

// Une URL ou un jeton manquant doit empecher le demarrage. Un service qui
// demarre sans jeton ne peut rien faire et le decouvre au premier appel.
func TestCharger_RefuseUneConfigIncomplete(t *testing.T) {
	cas := []struct {
		nom string
		env map[string]string
	}{
		{"sans URL", sans("HELLODATA_BASE_URL")},
		{"sans jeton", sans("HELLODATA_TOKEN")},
		{"sans URL webhook", sans("HELLODATA_WEBHOOK_URL")},
		{"sans jeton webhook", sans("HELLODATA_WEBHOOK_TOKEN")},
		{"tout absent", map[string]string{}},
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
	env := complete()
	env["MCP_PORT"] = "pas-un-nombre"
	poser(t, env)
	if _, err := Charger(); err == nil {
		t.Fatal("attendu une erreur sur un port illisible")
	}
}

func TestCharger_RetireLeSlashFinal(t *testing.T) {
	env := complete()
	env["HELLODATA_BASE_URL"] = "https://bo.example.test/admin/mcp/hellodata/"
	poser(t, env)
	c, _ := Charger()
	if c.BaseURL != "https://bo.example.test/admin/mcp/hellodata" {
		t.Errorf("BaseURL = %q, slash final non retire", c.BaseURL)
	}
}

func sans(cle string) map[string]string {
	env := complete()
	delete(env, cle)
	return env
}

// Controle positif des refus ci-dessus : l'environnement complet demarre,
// sinon un Charger qui refuse tout ferait passer ces tests.
func TestCharger_EnvironnementCompletDemarre(t *testing.T) {
	poser(t, complete())
	c, err := Charger()
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	if c.WebhookURL != "https://front.example.test/partenaires_externes/mcp/hellodata" || c.WebhookToken != "jeton-webhook" {
		t.Errorf("webhook = %q / %q", c.WebhookURL, c.WebhookToken)
	}
}
