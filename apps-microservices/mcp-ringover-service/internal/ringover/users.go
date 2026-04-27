package ringover

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
)

// User is a typed view of a single Ringover user.
// Ringover identifies users with numeric integer IDs (not UUIDs). Only the
// fields needed to populate the token-creation picker and derive teams are
// modelled.
type User struct {
	UserID    int    `json:"user_id"`
	TeamID    int    `json:"team_id,omitempty"`
	TeamName  string `json:"team_name,omitempty"`
	FirstName string `json:"firstname,omitempty"`
	LastName  string `json:"lastname,omitempty"`
	Email     string `json:"email,omitempty"`
}

// Team is a derived lightweight view of a Ringover team.
// Ringover does not expose a dedicated /teams endpoint on its public API, so
// teams are aggregated from the /users response.
type Team struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
}

// rawUser captures the Ringover /users response shape:
// { user_list: [ { user_id, team_id, team_name, firstname, lastname, email, ... } ] }
type rawUser struct {
	UserID    int    `json:"user_id"`
	TeamID    int    `json:"team_id"`
	TeamName  string `json:"team_name"`
	FirstName string `json:"firstname"`
	LastName  string `json:"lastname"`
	Email     string `json:"email"`
}

// DecodeUsers parses the raw JSON returned by GetUsers into a typed slice.
// The API envelope is tolerated in three shapes: `{ user_list: [...] }`
// (Ringover's documented shape), `{ data: [...] }` (older deployments), and a
// bare array (defensive fallback for proxies that unwrap envelopes).
func DecodeUsers(raw json.RawMessage) ([]User, error) {
	rawUsers, err := decodeUsersPayload(raw)
	if err != nil {
		return nil, err
	}
	out := make([]User, 0, len(rawUsers))
	for _, u := range rawUsers {
		out = append(out, User{
			UserID:    u.UserID,
			TeamID:    u.TeamID,
			TeamName:  u.TeamName,
			FirstName: u.FirstName,
			LastName:  u.LastName,
			Email:     u.Email,
		})
	}
	return out, nil
}

func decodeUsersPayload(raw json.RawMessage) ([]rawUser, error) {
	// Primary Ringover shape: { list_count: N, list: [...] }
	var withRingoverList struct {
		List []rawUser `json:"list"`
	}
	if err := json.Unmarshal(raw, &withRingoverList); err == nil && withRingoverList.List != nil {
		return withRingoverList.List, nil
	}
	// Alternate: { user_list: [...] } (older / monitoring-aware shape).
	var withUserList struct {
		UserList []rawUser `json:"user_list"`
	}
	if err := json.Unmarshal(raw, &withUserList); err == nil && withUserList.UserList != nil {
		return withUserList.UserList, nil
	}
	// Secondary: { data: [...] }
	var withData struct {
		Data []rawUser `json:"data"`
	}
	if err := json.Unmarshal(raw, &withData); err == nil && withData.Data != nil {
		return withData.Data, nil
	}
	// Fallback: bare array.
	var arr []rawUser
	if err := json.Unmarshal(raw, &arr); err == nil {
		return arr, nil
	}
	return nil, fmt.Errorf("users payload: unrecognised shape")
}

// TeamsFromUsers aggregates the distinct teams present in the users slice.
// Users without a team_id are ignored. Results are sorted by team name for
// deterministic UI rendering.
func TeamsFromUsers(users []User) []Team {
	seen := map[int]Team{}
	for _, u := range users {
		if u.TeamID == 0 {
			continue
		}
		if _, ok := seen[u.TeamID]; !ok {
			seen[u.TeamID] = Team{ID: u.TeamID, Name: u.TeamName}
		}
	}
	teams := make([]Team, 0, len(seen))
	for _, t := range seen {
		teams = append(teams, t)
	}
	sort.Slice(teams, func(i, j int) bool { return teams[i].Name < teams[j].Name })
	return teams
}

// UsersInTeams returns the user IDs of every user whose TeamID is in teamIDs.
// Used by the gateway when a token's filter mode is "teams".
func UsersInTeams(users []User, teamIDs []int) []int {
	if len(teamIDs) == 0 {
		return nil
	}
	want := make(map[int]struct{}, len(teamIDs))
	for _, id := range teamIDs {
		want[id] = struct{}{}
	}
	out := make([]int, 0)
	for _, u := range users {
		if _, ok := want[u.TeamID]; ok {
			out = append(out, u.UserID)
		}
	}
	return out
}

// FetchAllUsers calls GetUsers and returns the decoded list. Ringover's /users
// does not paginate (it returns the whole team or just the self user depending
// on Monitoring), so a single call is sufficient.
func (c *Client) FetchAllUsers(ctx context.Context) ([]User, error) {
	raw, err := c.GetUsers(ctx)
	if err != nil {
		return nil, err
	}
	return DecodeUsers(raw)
}
