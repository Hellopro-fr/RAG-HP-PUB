package db

import (
	"context"
	"strings"

	"gorm.io/gorm"
)

type RefreshTokenIssuer interface {
	NewRefreshToken(service string) string
}

func BootstrapRefreshTokens(ctx context.Context, g *gorm.DB, serviceMap map[string]string, issuer RefreshTokenIssuer) error {
	for apiPath := range serviceMap {
		serviceName := strings.TrimPrefix(apiPath, "/")
		var existing InfoRefreshToken
		err := g.WithContext(ctx).
			Where("nom_service = ? AND est_actif = ?", serviceName, true).
			First(&existing).Error
		if err == nil {
			continue
		}
		if err != gorm.ErrRecordNotFound {
			return err
		}
		row := InfoRefreshToken{
			NomService: serviceName,
			Token:      issuer.NewRefreshToken(serviceName),
			IPCreation: "system",
			EstActif:   true,
		}
		if err := g.WithContext(ctx).Create(&row).Error; err != nil {
			return err
		}
	}
	return nil
}
