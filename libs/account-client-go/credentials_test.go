package accountclient

import "testing"

func TestDeriveEnvKeys(t *testing.T) {
	id, sec := DeriveEnvKeys("api-gateway")
	if id != "ACCOUNT_CLIENT_ID_API_GATEWAY" {
		t.Errorf("id=%q", id)
	}
	if sec != "ACCOUNT_CLIENT_SECRET_API_GATEWAY" {
		t.Errorf("sec=%q", sec)
	}
}

func TestGetCredentials_PrefixedEnv(t *testing.T) {
	t.Setenv("SERVICE_NAME", "api-gateway")
	t.Setenv("ACCOUNT_CLIENT_ID_API_GATEWAY", "id-1")
	t.Setenv("ACCOUNT_CLIENT_SECRET_API_GATEWAY", "sec-1")
	id, sec, err := GetCredentials("")
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if id != "id-1" || sec != "sec-1" {
		t.Errorf("got=%q,%q", id, sec)
	}
}

func TestGetCredentials_FallsBackToPlain(t *testing.T) {
	t.Setenv("SERVICE_NAME", "lonely")
	t.Setenv("ACCOUNT_CLIENT_ID", "fallback-id")
	t.Setenv("ACCOUNT_CLIENT_SECRET", "fallback-sec")
	id, sec, err := GetCredentials("")
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if id != "fallback-id" || sec != "fallback-sec" {
		t.Errorf("got=%q,%q", id, sec)
	}
}

func TestGetCredentials_ExplicitArg(t *testing.T) {
	t.Setenv("ACCOUNT_CLIENT_ID_OTHER_THING", "id-2")
	t.Setenv("ACCOUNT_CLIENT_SECRET_OTHER_THING", "sec-2")
	id, sec, err := GetCredentials("other-thing")
	if err != nil {
		t.Fatalf("err=%v", err)
	}
	if id != "id-2" || sec != "sec-2" {
		t.Errorf("got=%q,%q", id, sec)
	}
}

func TestGetCredentials_MissingErrors(t *testing.T) {
	t.Setenv("SERVICE_NAME", "nope")
	for _, k := range []string{
		"ACCOUNT_CLIENT_ID_NOPE", "ACCOUNT_CLIENT_SECRET_NOPE",
		"ACCOUNT_CLIENT_ID", "ACCOUNT_CLIENT_SECRET",
	} {
		t.Setenv(k, "")
	}
	if _, _, err := GetCredentials(""); err == nil {
		t.Fatal("expected error")
	}
}
