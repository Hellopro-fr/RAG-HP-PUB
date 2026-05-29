package auth

import (
	"net/http"
	"testing"
)

func TestPolicyFor_UnknownService_FailOpen(t *testing.T) {
	snap := AuthSnapshot{}
	if got := snap.PolicyFor("ghost-service", http.MethodGet, "/x"); got != PolicyPublic {
		t.Fatalf("got=%v; want PolicyPublic", got)
	}
}

func TestPolicyFor_KnownService_DefaultBearer(t *testing.T) {
	snap := AuthSnapshot{
		"foo-service": ServicePolicy{Default: PolicyBearer},
	}
	if got := snap.PolicyFor("foo-service", "GET", "/x"); got != PolicyBearer {
		t.Fatalf("got=%v; want PolicyBearer", got)
	}
}

func TestPolicyFor_PublicPathBypass(t *testing.T) {
	snap := AuthSnapshot{
		"foo-service": ServicePolicy{
			Default:     PolicyBearer,
			PublicPaths: map[string]struct{}{"/healthz": {}},
		},
	}
	if got := snap.PolicyFor("foo-service", "GET", "/healthz"); got != PolicyPublic {
		t.Fatalf("got=%v; want PolicyPublic", got)
	}
}

func TestPolicyFor_EndpointOverrideWinsOverPublicPaths(t *testing.T) {
	snap := AuthSnapshot{
		"foo-service": ServicePolicy{
			Default:      PolicyPublic,
			PublicPaths:  map[string]struct{}{"/admin/burn": {}},
			EndpointAuth: map[string]AuthPolicy{"POST /admin/burn": PolicyAdminKey},
		},
	}
	if got := snap.PolicyFor("foo-service", "POST", "/admin/burn"); got != PolicyAdminKey {
		t.Fatalf("got=%v; want PolicyAdminKey (override wins over public_paths)", got)
	}
}

func TestPolicyFor_PathNormalization(t *testing.T) {
	snap := AuthSnapshot{
		"foo-service": ServicePolicy{
			Default:     PolicyBearer,
			PublicPaths: map[string]struct{}{"/dlq/queues": {}},
		},
	}
	cases := []string{"dlq/queues", "/dlq/queues", "dlq/queues/", "/dlq/queues/"}
	for _, p := range cases {
		if got := snap.PolicyFor("foo-service", "GET", p); got != PolicyPublic {
			t.Fatalf("path=%q got=%v; want PolicyPublic", p, got)
		}
	}
}
