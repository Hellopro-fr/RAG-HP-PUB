package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/hellopro/account-service/internal/auth"
)

type fakeUserResolver struct {
	isAdmin bool
}

func (f *fakeUserResolver) FindByEmail(email string) (UserInfo, error) {
	return UserInfo{
		Email:       email,
		DisplayName: "Alice",
		IsAdmin:     f.isAdmin,
		IsAllowed:   true,
	}, nil
}

func TestMeHandler_ReturnsCurrentUser(t *testing.T) {
	h := NewMeHandler(&fakeUserResolver{isAdmin: true})
	r := httptest.NewRequest(http.MethodGet, "/me", nil)
	ctx := context.WithValue(r.Context(), authSessionKey, &auth.SessionData{Email: "alice@example.com"})
	r = r.WithContext(ctx)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	var got map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["email"] != "alice@example.com" {
		t.Errorf("email=%v", got["email"])
	}
	if got["is_admin"] != true {
		t.Errorf("is_admin=%v", got["is_admin"])
	}
}
