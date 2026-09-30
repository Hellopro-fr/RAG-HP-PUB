package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

// Config porte tout ce que le service lit de son environnement.
// Aucune URL ni aucun jeton n'est code en dur (.claude/rules/security.md).
type Config struct {
	Port int
	// BaseURL du moteur /admin/mcp/hellodata sur Ecritel.
	BaseURL string
	// Token presente au moteur en Bearer.
	Token string
	// EmailsAutorises : adresses separees par des virgules, autorisees en
	// plus des admin. Les VALEURS ne sont jamais dans le code : le depot
	// est public.
	EmailsAutorises string
	// PublicURL sert a fabriquer les liens /download rendus au LLM.
	PublicURL string
}

func Charger() (Config, error) {
	c := Config{
		Port:            8597,
		BaseURL:         strings.TrimRight(os.Getenv("HELLODATA_BASE_URL"), "/"),
		Token:           os.Getenv("HELLODATA_TOKEN"),
		EmailsAutorises: os.Getenv("HELLODATA_ALLOWED_EMAILS"),
		PublicURL:       strings.TrimRight(os.Getenv("HELLODATA_PUBLIC_URL"), "/"),
	}
	if v := os.Getenv("MCP_PORT"); v != "" {
		p, err := strconv.Atoi(v)
		if err != nil || p < 1 || p > 65535 {
			return Config{}, fmt.Errorf("MCP_PORT invalide: %q", v)
		}
		c.Port = p
	}
	if c.BaseURL == "" {
		return Config{}, fmt.Errorf("HELLODATA_BASE_URL est requis")
	}
	if c.Token == "" {
		return Config{}, fmt.Errorf("HELLODATA_TOKEN est requis")
	}
	return c, nil
}
