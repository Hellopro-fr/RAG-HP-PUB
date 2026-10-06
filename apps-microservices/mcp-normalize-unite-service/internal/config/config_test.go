package config

import "testing"

func TestUnitWriteToolsEnabledIsOptIn(t *testing.T) {
	cases := map[string]bool{
		"": false, "false": false, "0": false, "no": false, "on": false,
		"true": true, "TRUE": true, "1": true, "yes": true, "Yes": true, " true ": true,
	}
	for value, want := range cases {
		t.Setenv("UNIT_WRITE_TOOLS_ENABLED", value)
		if got := Load().UnitWriteToolsEnabled; got != want {
			t.Errorf("UNIT_WRITE_TOOLS_ENABLED=%q -> %v, want %v", value, got, want)
		}
	}
}
