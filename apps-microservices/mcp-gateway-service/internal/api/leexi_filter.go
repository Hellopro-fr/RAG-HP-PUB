package api

import (
	"context"
	"encoding/json"
	"fmt"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/leexiadmin"
)

// validLeexiFilterModes lists the accepted Mode values. Anything else is
// rejected at the API boundary so we never persist garbage.
var validLeexiFilterModes = map[string]struct{}{
	LeexiFilterModeNone:    {},
	LeexiFilterModeUsers:   {},
	LeexiFilterModeTeams:   {},
	LeexiFilterModeCreator: {},
}

// resolveLeexiFilterForCreate validates a LeexiFilterDTO and returns the
// fields ready to assign on the DB row.
//
// callerEmail is used only when filter.Mode == "creator" — the email is
// translated to a Leexi user UUID via the leexiadmin client.
//
// adminClient may be nil when no Leexi integration is configured: in that
// case all modes other than "none" are rejected with an error to avoid
// persisting unenforceable scopes.
func resolveLeexiFilterForCreate(
	ctx context.Context,
	adminClient *leexiadmin.Client,
	filter *LeexiFilterDTO,
	callerEmail string,
) (mode string, userUUIDs json.RawMessage, teamUUIDs json.RawMessage, err error) {
	if filter == nil || filter.Mode == "" {
		return LeexiFilterModeNone, nil, nil, nil
	}

	if _, ok := validLeexiFilterModes[filter.Mode]; !ok {
		return "", nil, nil, fmt.Errorf("invalid leexi_filter.mode %q", filter.Mode)
	}

	switch filter.Mode {
	case LeexiFilterModeNone:
		return LeexiFilterModeNone, nil, nil, nil

	case LeexiFilterModeUsers:
		if len(filter.UserUUIDs) == 0 {
			return "", nil, nil, fmt.Errorf("leexi_filter.user_uuids is required when mode = users")
		}
		raw, mErr := json.Marshal(filter.UserUUIDs)
		if mErr != nil {
			return "", nil, nil, fmt.Errorf("encode user_uuids: %w", mErr)
		}
		return LeexiFilterModeUsers, raw, nil, nil

	case LeexiFilterModeTeams:
		if len(filter.TeamUUIDs) == 0 {
			return "", nil, nil, fmt.Errorf("leexi_filter.team_uuids is required when mode = teams")
		}
		raw, mErr := json.Marshal(filter.TeamUUIDs)
		if mErr != nil {
			return "", nil, nil, fmt.Errorf("encode team_uuids: %w", mErr)
		}
		return LeexiFilterModeTeams, nil, raw, nil

	case LeexiFilterModeCreator:
		if !adminClient.Enabled() {
			return "", nil, nil, fmt.Errorf("leexi admin integration is not configured (set LEEXI_INTERNAL_URL and LEEXI_ADMIN_TOKEN)")
		}
		if callerEmail == "" {
			return "", nil, nil, fmt.Errorf("cannot resolve creator: no authenticated user email available")
		}
		user, fErr := adminClient.FindUserByEmail(ctx, callerEmail)
		if fErr != nil {
			return "", nil, nil, fmt.Errorf("creator email %q has no matching Leexi user: %w", callerEmail, fErr)
		}
		raw, mErr := json.Marshal([]string{user.UUID})
		if mErr != nil {
			return "", nil, nil, fmt.Errorf("encode creator UUID: %w", mErr)
		}
		return LeexiFilterModeCreator, raw, nil, nil
	}

	// Unreachable: validLeexiFilterModes guards every branch above.
	return "", nil, nil, fmt.Errorf("unhandled leexi_filter.mode %q", filter.Mode)
}

// scopeTokenLeexiFilterToDTO renders the persisted columns into the response
// DTO. Returns nil when the token is unrestricted so the JSON omits the field.
func scopeTokenLeexiFilterToDTO(t *db.ScopeToken) *LeexiFilterDTO {
	return leexiFilterToDTO(t.LeexiFilterMode, t.LeexiAllowedUserUUIDs, t.LeexiAllowedTeamUUIDs)
}

// oauth2ClientLeexiFilterToDTO renders the persisted columns of an OAuth2
// client. Same shape as scopeTokenLeexiFilterToDTO.
func oauth2ClientLeexiFilterToDTO(c *db.OAuth2Client) *LeexiFilterDTO {
	return leexiFilterToDTO(c.LeexiFilterMode, c.LeexiAllowedUserUUIDs, c.LeexiAllowedTeamUUIDs)
}

func leexiFilterToDTO(mode string, users, teams json.RawMessage) *LeexiFilterDTO {
	if mode == "" || mode == LeexiFilterModeNone {
		return nil
	}
	dto := &LeexiFilterDTO{Mode: mode}
	if len(users) > 0 {
		_ = json.Unmarshal(users, &dto.UserUUIDs)
	}
	if len(teams) > 0 {
		_ = json.Unmarshal(teams, &dto.TeamUUIDs)
	}
	if mode == LeexiFilterModeCreator && len(dto.UserUUIDs) > 0 {
		dto.CreatorUUID = dto.UserUUIDs[0]
	}
	return dto
}
