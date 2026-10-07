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
	// PublicURL sert a fabriquer les liens /download rendus au LLM.
	PublicURL string
	// WebhookURL : base du webhook FRONT partenaires_externes/mcp/hellodata,
	// qui enregistre les reponses de campagne.
	WebhookURL string
	// WebhookToken : Bearer propre au webhook, distinct de Token.
	WebhookToken string
}

func Charger() (Config, error) {
	c := Config{
		Port:         8597,
		BaseURL:      strings.TrimRight(os.Getenv("HELLODATA_BASE_URL"), "/"),
		Token:        os.Getenv("HELLODATA_TOKEN"),
		PublicURL:    strings.TrimRight(os.Getenv("HELLODATA_PUBLIC_URL"), "/"),
		WebhookURL:   strings.TrimRight(os.Getenv("HELLODATA_WEBHOOK_URL"), "/"),
		WebhookToken: os.Getenv("HELLODATA_WEBHOOK_TOKEN"),
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
	if c.WebhookURL == "" {
		return Config{}, fmt.Errorf("HELLODATA_WEBHOOK_URL est requis")
	}
	if c.WebhookToken == "" {
		return Config{}, fmt.Errorf("HELLODATA_WEBHOOK_TOKEN est requis")
	}
	return c, nil
}
