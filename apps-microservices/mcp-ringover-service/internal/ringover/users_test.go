package ringover

import (
	"encoding/json"
	"reflect"
	"sort"
	"testing"
)

func TestDecodeUsers_UserListEnvelope(t *testing.T) {
	// Ringover /users returns { user_list: [ {...} ] } when Monitoring is ON.
	raw := json.RawMessage(`{
		"user_list": [
			{"user_id": 123, "team_id": 7, "firstname": "Alice", "lastname": "Dupont", "email": "a@x.fr", "concat_name": "Alice Dupont"},
			{"user_id": 456, "team_id": 7, "firstname": "Bob", "lastname": "Martin", "email": "b@x.fr"},
			{"user_id": 789, "team_id": 9, "firstname": "Carol", "lastname": "Durand", "email": "c@x.fr"}
		]
	}`)
	users, err := DecodeUsers(raw)
	if err != nil {
		t.Fatalf("DecodeUsers: %v", err)
	}
	if len(users) != 3 {
		t.Fatalf("expected 3 users, got %d", len(users))
	}
	if users[0].UserID != 123 || users[0].FirstName != "Alice" || users[0].TeamID != 7 {
		t.Errorf("users[0] = %+v", users[0])
	}
}

func TestDecodeUsers_BareArray(t *testing.T) {
	raw := json.RawMessage(`[{"user_id": 1, "firstname": "A", "lastname": "B"}]`)
	users, err := DecodeUsers(raw)
	if err != nil {
		t.Fatalf("DecodeUsers: %v", err)
	}
	if len(users) != 1 || users[0].UserID != 1 {
		t.Errorf("unexpected: %+v", users)
	}
}

func TestDecodeUsers_TeamNameFallbackFromUser(t *testing.T) {
	// Some deployments emit team info as a flat team_name rather than a lookup.
	raw := json.RawMessage(`{"user_list":[{"user_id": 10, "team_id": 1, "team_name": "Sales"}]}`)
	users, err := DecodeUsers(raw)
	if err != nil {
		t.Fatalf("DecodeUsers: %v", err)
	}
	if users[0].TeamName != "Sales" {
		t.Errorf("expected TeamName=Sales, got %q", users[0].TeamName)
	}
}

func TestTeamsFromUsers_DistinctAndSorted(t *testing.T) {
	users := []User{
		{UserID: 1, TeamID: 7, TeamName: "Sales"},
		{UserID: 2, TeamID: 7, TeamName: "Sales"},
		{UserID: 3, TeamID: 9, TeamName: "Engineering"},
		{UserID: 4, TeamID: 0, TeamName: ""}, // no team — dropped
	}
	teams := TeamsFromUsers(users)
	if len(teams) != 2 {
		t.Fatalf("expected 2 distinct teams, got %d", len(teams))
	}
	// Sorted alphabetically by name.
	if teams[0].Name != "Engineering" || teams[1].Name != "Sales" {
		t.Errorf("unexpected ordering: %+v", teams)
	}
}

func TestUsersInTeams(t *testing.T) {
	users := []User{
		{UserID: 1, TeamID: 7},
		{UserID: 2, TeamID: 7},
		{UserID: 3, TeamID: 9},
		{UserID: 4, TeamID: 9},
		{UserID: 5, TeamID: 11},
	}
	got := UsersInTeams(users, []int{7, 9})
	sort.Ints(got)
	want := []int{1, 2, 3, 4}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("UsersInTeams = %v, want %v", got, want)
	}

	if res := UsersInTeams(users, nil); res != nil {
		t.Errorf("expected nil for empty team list, got %v", res)
	}
}
