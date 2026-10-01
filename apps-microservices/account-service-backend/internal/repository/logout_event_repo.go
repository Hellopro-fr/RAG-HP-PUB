package repository

import (
	"time"

	"account-service/internal/db"
	"gorm.io/gorm"
)

type LogoutEventRepo struct {
	g *gorm.DB
}

func NewLogoutEventRepo(g *gorm.DB) *LogoutEventRepo {
	return &LogoutEventRepo{g: g}
}

func (r *LogoutEventRepo) Create(e *db.LogoutEvent) error {
	if e.Status == "" {
		e.Status = "pending"
	}
	return r.g.Create(e).Error
}

func (r *LogoutEventRepo) PickPending(limit int) ([]db.LogoutEvent, error) {
	var out []db.LogoutEvent
	err := r.g.Where("status = ? AND next_attempt_at <= ?", "pending", time.Now()).
		Order("next_attempt_at ASC").Limit(limit).Find(&out).Error
	return out, err
}

func (r *LogoutEventRepo) MarkSent(id string) error {
	return r.g.Model(&db.LogoutEvent{}).Where("id = ?", id).Updates(map[string]interface{}{
		"status":     "sent",
		"updated_at": time.Now(),
	}).Error
}

func (r *LogoutEventRepo) MarkFailed(id, errMsg string) error {
	return r.g.Model(&db.LogoutEvent{}).Where("id = ?", id).Updates(map[string]interface{}{
		"status":     "failed",
		"last_error": errMsg,
		"updated_at": time.Now(),
	}).Error
}

func (r *LogoutEventRepo) Reschedule(id string, attempts int, nextAt time.Time, errMsg string) error {
	return r.g.Model(&db.LogoutEvent{}).Where("id = ?", id).Updates(map[string]interface{}{
		"status":          "pending",
		"attempts":        attempts,
		"next_attempt_at": nextAt,
		"last_error":      errMsg,
		"updated_at":      time.Now(),
	}).Error
}
