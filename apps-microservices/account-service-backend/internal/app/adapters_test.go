package app

import "testing"

// Compile-only sanity check on the adapter types. Real wiring is exercised
// end-to-end via the http handlers in cmd/server.
func TestAdaptersTypes(t *testing.T) {
	var _ = cryptoAdapter{}
	var _ = userInfoAdapter{}
	var _ = logoutRedirectLookup{}
	var _ = userBroadcastAdapter{}
	var _ = dbPinger{}
}
