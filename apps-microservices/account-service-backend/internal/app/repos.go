package app

import (
	"gorm.io/gorm"

	"account-service/internal/repository"
)

// Repos is the bundle of GORM-backed repositories the rest of the app
// depends on. Built once at boot in BuildRepos and passed by value so
// route registration doesn't need direct DB access.
type Repos struct {
	User     *repository.UserRepo
	OAuth2   *repository.OAuth2ClientRepo
	AuthCode *repository.AuthCodeRepo
	Refresh  *repository.RefreshRepo
	Logout   *repository.LogoutEventRepo
	Audit    *repository.AuditRepo
}

// BuildRepos wires every GORM-backed repository against a single *gorm.DB.
// Pulled out of main() to lower the coupling/centrality of the entry point —
// the graphify centrality analysis flagged main() as a 19-community bridge,
// and bundling the repos keeps them in their own community here.
func BuildRepos(g *gorm.DB, adminEmails []string) Repos {
	return Repos{
		User:     repository.NewUserRepo(g, adminEmails),
		OAuth2:   repository.NewOAuth2ClientRepo(g),
		AuthCode: repository.NewAuthCodeRepo(g),
		Refresh:  repository.NewRefreshRepo(g),
		Logout:   repository.NewLogoutEventRepo(g),
		Audit:    repository.NewAuditRepo(g),
	}
}
