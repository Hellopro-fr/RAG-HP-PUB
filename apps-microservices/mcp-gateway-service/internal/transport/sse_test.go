package transport

import "testing"

// TestNewSSEServerNoHandler confirms the constructor accepts a bare handler
// and initialises the session map.
func TestNewSSEServerNoHandler(t *testing.T) {
	s := NewSSEServer(nil)
	if s == nil {
		t.Fatal("expected non-nil SSEServer")
	}
	if s.sessions == nil {
		t.Error("sessions map should be initialised")
	}
}
