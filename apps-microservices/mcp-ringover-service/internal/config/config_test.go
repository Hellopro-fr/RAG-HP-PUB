package config

import "testing"

func TestLoad_DefaultCountryCode(t *testing.T) {
	t.Setenv("RINGOVER_DEFAULT_COUNTRY_CODE", "")
	if got := Load().DefaultCountryCode; got != "33" {
		t.Errorf("default DefaultCountryCode = %q, want 33", got)
	}
	t.Setenv("RINGOVER_DEFAULT_COUNTRY_CODE", "1")
	if got := Load().DefaultCountryCode; got != "1" {
		t.Errorf("override DefaultCountryCode = %q, want 1", got)
	}
}
