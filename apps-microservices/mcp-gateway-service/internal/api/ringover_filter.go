package api

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/ringoveradmin"
)

// validRingoverFilterModes lists the accepted Mode values. Anything else is
// rejected at the API boundary so we never persist garbage.
var validRingoverFilterModes = map[string]struct{}{
	RingoverFilterModeNone:    {},
	RingoverFilterModeUsers:   {},
	RingoverFilterModeTeams:   {},
	RingoverFilterModeCreator: {},
}

// resolveRingoverFilterForCreate validates a RingoverFilterDTO and returns the
// fields ready to assign on the DB row (JSON-encoded int arrays).
//
// callerEmail is used only when filter.Mode == "creator" — the email is
// translated to a Ringover numeric user_id via the ringoveradmin client.
//
// adminClient may be nil when no Ringover integration is configured: in that
// case all modes other than "none" are rejected with an error to avoid
// persisting unenforceable scopes.
func resolveRingoverFilterForCreate(
	ctx context.Context,
	adminClient *ringoveradmin.Client,
	filter *RingoverFilterDTO,
	callerEmail string,
) (mode string, userIDs json.RawMessage, teamIDs json.RawMessage, err error) {
	if filter == nil || filter.Mode == "" {
		return RingoverFilterModeNone, nil, nil, nil
	}

	if _, ok := validRingoverFilterModes[filter.Mode]; !ok {
		return "", nil, nil, fmt.Errorf("invalid ringover_filter.mode %q", filter.Mode)
	}

	switch filter.Mode {
	case RingoverFilterModeNone:
		return RingoverFilterModeNone, nil, nil, nil

	case RingoverFilterModeUsers:
		if len(filter.UserIDs) == 0 {
			return "", nil, nil, fmt.Errorf("ringover_filter.user_ids is required when mode = users")
		}
		raw, mErr := json.Marshal(filter.UserIDs)
		if mErr != nil {
			return "", nil, nil, fmt.Errorf("encode user_ids: %w", mErr)
		}
		return RingoverFilterModeUsers, raw, nil, nil

	case RingoverFilterModeTeams:
		if len(filter.TeamIDs) == 0 {
			return "", nil, nil, fmt.Errorf("ringover_filter.team_ids is required when mode = teams")
		}
		raw, mErr := json.Marshal(filter.TeamIDs)
		if mErr != nil {
			return "", nil, nil, fmt.Errorf("encode team_ids: %w", mErr)
		}
		return RingoverFilterModeTeams, nil, raw, nil

	case RingoverFilterModeCreator:
		if !adminClient.Enabled() {
			return "", nil, nil, fmt.Errorf("ringover admin integration is not configured (set RINGOVER_INTERNAL_URL and RINGOVER_ADMIN_TOKEN)")
		}
		if callerEmail == "" {
			return "", nil, nil, fmt.Errorf("cannot resolve creator: no authenticated user email available")
		}
		user, fErr := adminClient.FindUserByEmail(ctx, callerEmail)
		if fErr != nil {
			return "", nil, nil, fmt.Errorf("creator email %q has no matching Ringover user: %w", callerEmail, fErr)
		}
		raw, mErr := json.Marshal([]int{user.UserID})
		if mErr != nil {
			return "", nil, nil, fmt.Errorf("encode creator user_id: %w", mErr)
		}
		return RingoverFilterModeCreator, raw, nil, nil
	}

	return "", nil, nil, fmt.Errorf("unhandled ringover_filter.mode %q", filter.Mode)
}

// scopeTokenRingoverFilterToDTO renders the persisted columns into the
// response DTO. Returns nil when the token is unrestricted so the JSON omits
// the field.
func scopeTokenRingoverFilterToDTO(t *db.ScopeToken) *RingoverFilterDTO {
	return ringoverFilterToDTO(t.RingoverFilterMode, t.RingoverAllowedUserIDs, t.RingoverAllowedTeamIDs)
}

// oauth2ClientRingoverFilterToDTO renders the persisted columns of an OAuth2
// client. Same shape as scopeTokenRingoverFilterToDTO.
func oauth2ClientRingoverFilterToDTO(c *db.OAuth2Client) *RingoverFilterDTO {
	return ringoverFilterToDTO(c.RingoverFilterMode, c.RingoverAllowedUserIDs, c.RingoverAllowedTeamIDs)
}

func ringoverFilterToDTO(mode string, users, teams json.RawMessage) *RingoverFilterDTO {
	if mode == "" || mode == RingoverFilterModeNone {
		return nil
	}
	dto := &RingoverFilterDTO{Mode: mode}
	if len(users) > 0 {
		_ = json.Unmarshal(users, &dto.UserIDs)
	}
	if len(teams) > 0 {
		_ = json.Unmarshal(teams, &dto.TeamIDs)
	}
	if mode == RingoverFilterModeCreator && len(dto.UserIDs) > 0 {
		dto.CreatorUserID = dto.UserIDs[0]
	}
	return dto
}
