package tools

import (
	"encoding/json"
	"testing"
)

func TestSchemaConstants_ValidJSON(t *testing.T) {
	cases := map[string]string{
		"classifyInputSchema":      classifyInputSchema,
		"classifyBatchInputSchema": classifyBatchInputSchema,
	}
	for name, raw := range cases {
		var obj any
		if err := json.Unmarshal([]byte(raw), &obj); err != nil {
			t.Errorf("%s is not valid JSON: %v", name, err)
		}
	}
}
