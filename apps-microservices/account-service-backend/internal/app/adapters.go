package app

import (
	"encoding/json"

	"gorm.io/gorm"

	"github.com/hellopro/account-service/internal/api"
	"github.com/hellopro/account-service/internal/crypto"
	"github.com/hellopro/account-service/internal/db"
	"github.com/hellopro/account-service/internal/logout"
	"github.com/hellopro/account-service/internal/repository"
)

// cryptoAdapter narrows *crypto.Cipher down to logout.Decrypter so the
// broadcaster only sees the operation it needs.
type cryptoAdapter struct {
	c *crypto.Cipher
}

func (a cryptoAdapter) Decrypt(in []byte) ([]byte, error) { return a.c.Decrypt(in) }

// dbPinger satisfies health.Pinger over a *gorm.DB. Lives here rather than in
// internal/health to avoid having that package import GORM.
type dbPinger struct {
	g *gorm.DB
}

func (p dbPinger) Ping() error {
	sqlDB, err := p.g.DB()
	if err != nil {
		return err
	}
	return sqlDB.Ping()
}

// userInfoAdapter projects a repository.UserRepo row down to api.UserInfo so
// the /me handler doesn't need to know about GORM.
type userInfoAdapter struct {
	repo *repository.UserRepo
}

func (a userInfoAdapter) FindByEmail(email string) (api.UserInfo, error) {
	u, err := a.repo.FindByEmail(email)
	if err != nil {
		return api.UserInfo{}, err
	}
	return api.UserInfo{
		Email:       u.Email,
		DisplayName: u.DisplayName,
		IsAdmin:     u.IsAdmin,
		IsAllowed:   u.IsAllowed,
	}, nil
}

// logoutRedirectLookup implements auth.LogoutRedirectLookup over the existing
// OAuth2ClientRepo. The redirect_uris column is a JSON array stored as
// *string; parsed lazily on each call since /logout is low-traffic.
type logoutRedirectLookup struct {
	repo *repository.OAuth2ClientRepo
}

func (l logoutRedirectLookup) GetClientRedirectURIs(clientID string) ([]string, error) {
	c, err := l.repo.GetByClientID(clientID)
	if err != nil {
		return nil, err
	}
	if c.RedirectURIs == nil || *c.RedirectURIs == "" {
		return nil, nil
	}
	var uris []string
	if err := json.Unmarshal([]byte(*c.RedirectURIs), &uris); err != nil {
		return nil, err
	}
	return uris, nil
}

// userBroadcastAdapter resolves which OAuth2 clients a given user has active
// refresh tokens for, then fans the logout event out through the broadcaster.
// Backs the api.AdminUserDeps.Broadcaster contract.
type userBroadcastAdapter struct {
	clients *repository.OAuth2ClientRepo
	refresh *repository.RefreshRepo
	bc      *logout.Broadcaster
}

func (a userBroadcastAdapter) BroadcastForUser(email string) {
	rows, err := a.refresh.ListByUser(email)
	if err != nil {
		return
	}
	clientIDs := map[string]struct{}{}
	for _, r := range rows {
		clientIDs[r.ClientID] = struct{}{}
	}
	clients := make([]db.OAuth2Client, 0, len(clientIDs))
	for cid := range clientIDs {
		c, err := a.clients.GetByClientID(cid)
		if err != nil {
			continue
		}
		clients = append(clients, *c)
	}
	a.bc.Broadcast(email, "", clients)
}
