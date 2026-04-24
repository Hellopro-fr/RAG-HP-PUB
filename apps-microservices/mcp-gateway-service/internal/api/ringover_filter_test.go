package api

import (
	"context"
	"encoding/json"
	"reflect"
	"testing"

	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/ringoveradmin"
)

func TestResolveRingoverFilterForCreate_Nil(t *testing.T) {
	mode, u, te, err := resolveRingoverFilterForCreate(context.Background(), nil, nil, "")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if mode != RingoverFilterModeNone || u != nil || te != nil {
		t.Errorf("expected (none, nil, nil), got (%s, %v, %v)", mode, u, te)
	}
}

func TestResolveRingoverFilterForCreate_InvalidMode(t *testing.T) {
	_, _, _, err := resolveRingoverFilterForCreate(
		context.Background(), nil, &RingoverFilterDTO{Mode: "bogus"}, "",
	)
	if err == nil {
		t.Fatal("expected error for invalid mode")
	}
}

func TestResolveRingoverFilterForCreate_UsersRequiresIDs(t *testing.T) {
	_, _, _, err := resolveRingoverFilterForCreate(
		context.Background(), nil, &RingoverFilterDTO{Mode: RingoverFilterModeUsers}, "",
	)
	if err == nil {
		t.Fatal("expected error for empty user_ids")
	}
}

func TestResolveRingoverFilterForCreate_UsersOK(t *testing.T) {
	mode, u, te, err := resolveRingoverFilterForCreate(
		context.Background(), nil, &RingoverFilterDTO{Mode: RingoverFilterModeUsers, UserIDs: []int{10, 20}}, "",
	)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if mode != RingoverFilterModeUsers || te != nil {
		t.Errorf("mode=%s, team=%v", mode, te)
	}
	var decoded []int
	if err := json.Unmarshal(u, &decoded); err != nil {
		t.Fatalf("unmarshal users: %v", err)
	}
	if !reflect.DeepEqual(decoded, []int{10, 20}) {
		t.Errorf("got %v", decoded)
	}
}

func TestResolveRingoverFilterForCreate_TeamsOK(t *testing.T) {
	mode, u, te, err := resolveRingoverFilterForCreate(
		context.Background(), nil, &RingoverFilterDTO{Mode: RingoverFilterModeTeams, TeamIDs: []int{7}}, "",
	)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if mode != RingoverFilterModeTeams || u != nil {
		t.Errorf("mode=%s, user=%v", mode, u)
	}
	var decoded []int
	if err := json.Unmarshal(te, &decoded); err != nil {
		t.Fatalf("unmarshal teams: %v", err)
	}
	if !reflect.DeepEqual(decoded, []int{7}) {
		t.Errorf("got %v", decoded)
	}
}

func TestResolveRingoverFilterForCreate_CreatorWithoutAdmin(t *testing.T) {
	// admin client disabled (empty url/token) → reject creator mode.
	disabled := ringoveradmin.NewClient("", "")
	_, _, _, err := resolveRingoverFilterForCreate(
		context.Background(), disabled, &RingoverFilterDTO{Mode: RingoverFilterModeCreator}, "x@y.fr",
	)
	if err == nil {
		t.Fatal("expected error when admin client is disabled")
	}
}

func TestRingoverFilterToDTO_None(t *testing.T) {
	if dto := ringoverFilterToDTO(RingoverFilterModeNone, nil, nil); dto != nil {
		t.Errorf("expected nil DTO for mode=none, got %+v", dto)
	}
	if dto := ringoverFilterToDTO("", nil, nil); dto != nil {
		t.Errorf("expected nil DTO for empty mode, got %+v", dto)
	}
}

func TestRingoverFilterToDTO_Creator(t *testing.T) {
	raw, _ := json.Marshal([]int{42})
	dto := ringoverFilterToDTO(RingoverFilterModeCreator, raw, nil)
	if dto == nil || dto.CreatorUserID != 42 {
		t.Errorf("unexpected: %+v", dto)
	}
}

func TestScopeTokenAndOAuth2Mappers(t *testing.T) {
	raw, _ := json.Marshal([]int{1, 2})
	token := &db.ScopeToken{
		RingoverFilterMode:     RingoverFilterModeUsers,
		RingoverAllowedUserIDs: raw,
	}
	dto := scopeTokenRingoverFilterToDTO(token)
	if dto == nil || dto.Mode != RingoverFilterModeUsers || len(dto.UserIDs) != 2 {
		t.Errorf("scopeToken map: %+v", dto)
	}

	client := &db.OAuth2Client{
		RingoverFilterMode:     RingoverFilterModeUsers,
		RingoverAllowedUserIDs: raw,
	}
	dto = oauth2ClientRingoverFilterToDTO(client)
	if dto == nil || dto.Mode != RingoverFilterModeUsers || len(dto.UserIDs) != 2 {
		t.Errorf("oauth2 map: %+v", dto)
	}
}
