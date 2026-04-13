package leexi

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
)

// User is a typed view of a single Leexi workspace user.
// Only the fields needed to populate the MCP token-creation picker are
// modelled; the original JSON is preserved via unexported `raw` for callers
// that need additional attributes.
type User struct {
	UUID      string `json:"uuid"`
	Email     string `json:"email,omitempty"`
	FirstName string `json:"first_name,omitempty"`
	LastName  string `json:"last_name,omitempty"`
	// Team fields may be returned either as a nested object or as a flat
	// `team_uuid` / `team_name`. Both shapes are normalised at decode time.
	TeamUUID string `json:"team_uuid,omitempty"`
	TeamName string `json:"team_name,omitempty"`
}

// Team is a derived lightweight view of a Leexi team.
// Leexi does not expose a dedicated /teams endpoint today, so teams are
// aggregated from the users response.
type Team struct {
	UUID string `json:"uuid"`
	Name string `json:"name"`
}

// rawUser captures every shape Leexi has returned for users: either a flat
// object with team_uuid/team_name or a nested team object. The public API
// today exposes a single "name" field rather than first_name/last_name, but
// both shapes are tolerated for forward-compatibility.
type rawUser struct {
	UUID      string          `json:"uuid"`
	Email     string          `json:"email"`
	Name      string          `json:"name"`
	FirstName string          `json:"first_name"`
	LastName  string          `json:"last_name"`
	TeamUUID  string          `json:"team_uuid"`
	TeamName  string          `json:"team_name"`
	Team      json.RawMessage `json:"team"`
}

type rawTeam struct {
	UUID string `json:"uuid"`
	Name string `json:"name"`
}

// DecodeUsers parses the raw JSON returned by ListUsers into a typed slice.
// The API envelope is tolerated in two shapes: either a bare array, or an
// object with a "data" field wrapping the array.
func DecodeUsers(raw json.RawMessage) ([]User, error) {
	users, err := decodeUsersPayload(raw)
	if err != nil {
		return nil, err
	}

	out := make([]User, 0, len(users))
	for _, u := range users {
		first, last := u.FirstName, u.LastName
		// Split the "name" field when explicit first/last are not provided.
		// Leexi's public API returns either a single token (e.g. "Alice") or
		// a "First Last" pair (e.g. "Gustave Rihal"); any extra tokens are
		// folded into the first name so "Jean-Paul De Villiers" renders as
		// first="Jean-Paul De", last="Villiers".
		if first == "" && last == "" && u.Name != "" {
			parts := strings.Fields(u.Name)
			switch len(parts) {
			case 0:
				// nothing
			case 1:
				last = parts[0]
			default:
				first = strings.Join(parts[:len(parts)-1], " ")
				last = parts[len(parts)-1]
			}
		}
		user := User{
			UUID:      u.UUID,
			Email:     u.Email,
			FirstName: first,
			LastName:  last,
			TeamUUID:  u.TeamUUID,
			TeamName:  u.TeamName,
		}
		// Normalise nested team object if present.
		if len(u.Team) > 0 && string(u.Team) != "null" {
			var t rawTeam
			if err := json.Unmarshal(u.Team, &t); err == nil {
				if user.TeamUUID == "" {
					user.TeamUUID = t.UUID
				}
				if user.TeamName == "" {
					user.TeamName = t.Name
				}
			}
		}
		out = append(out, user)
	}
	return out, nil
}

// decodeUsersPayload strips any "data" envelope and returns the raw user list.
func decodeUsersPayload(raw json.RawMessage) ([]rawUser, error) {
	// First try: bare array.
	var arr []rawUser
	if err := json.Unmarshal(raw, &arr); err == nil {
		return arr, nil
	}
	// Fallback: object with a "data" array field.
	var env struct {
		Data []rawUser `json:"data"`
	}
	if err := json.Unmarshal(raw, &env); err != nil {
		return nil, fmt.Errorf("users payload: neither array nor {data: []}: %w", err)
	}
	return env.Data, nil
}

// TeamsFromUsers aggregates the distinct teams present in the users slice.
// Results are sorted by team name for deterministic UI rendering.
func TeamsFromUsers(users []User) []Team {
	seen := map[string]Team{}
	for _, u := range users {
		if u.TeamUUID == "" {
			continue
		}
		if _, ok := seen[u.TeamUUID]; !ok {
			seen[u.TeamUUID] = Team{UUID: u.TeamUUID, Name: u.TeamName}
		}
	}
	teams := make([]Team, 0, len(seen))
	for _, t := range seen {
		teams = append(teams, t)
	}
	sort.Slice(teams, func(i, j int) bool { return teams[i].Name < teams[j].Name })
	return teams
}

// UsersInTeams returns the UUIDs of every user whose TeamUUID is in teamUUIDs.
// Used by the gateway when a token's filter mode is "teams".
func UsersInTeams(users []User, teamUUIDs []string) []string {
	if len(teamUUIDs) == 0 {
		return nil
	}
	want := make(map[string]struct{}, len(teamUUIDs))
	for _, id := range teamUUIDs {
		want[id] = struct{}{}
	}
	out := make([]string, 0)
	for _, u := range users {
		if _, ok := want[u.TeamUUID]; ok {
			out = append(out, u.UUID)
		}
	}
	return out
}

// FetchAllUsers paginates through the Leexi /users endpoint until an empty
// page is returned. Uses items=100 (API maximum) to minimise calls.
func (c *Client) FetchAllUsers(ctx context.Context) ([]User, error) {
	const pageSize = 100
	var all []User
	for page := 1; ; page++ {
		raw, err := c.ListUsers(ctx, page, pageSize)
		if err != nil {
			return nil, err
		}
		batch, err := DecodeUsers(raw)
		if err != nil {
			return nil, err
		}
		all = append(all, batch...)
		if len(batch) < pageSize {
			break
		}
	}
	return all, nil
}
