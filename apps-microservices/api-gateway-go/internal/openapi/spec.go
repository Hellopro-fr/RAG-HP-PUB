package openapi

import (
	_ "embed"

	"gopkg.in/yaml.v3"
)

//go:embed base.yaml
var baseYAML []byte

func LoadBaseSpec() (map[string]any, error) {
	var m map[string]any
	if err := yaml.Unmarshal(baseYAML, &m); err != nil {
		return nil, err
	}
	return m, nil
}
