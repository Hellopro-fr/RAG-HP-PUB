package gateway

import (
	"testing"
)

func TestNewGateway(t *testing.T) {
	reg := NewRegistry()
	gw := New("test-gw", "1.0.0", reg)
	if gw == nil {
		t.Fatal("expected non-nil gateway")
	}
	if gw.name != "test-gw" {
		t.Errorf("expected name test-gw, got %s", gw.name)
	}
}
