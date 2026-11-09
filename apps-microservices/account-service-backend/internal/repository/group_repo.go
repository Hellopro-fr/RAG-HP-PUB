package repository

import (
	"errors"
	"strings"
	"time"

	"account-service/internal/db"
	"github.com/go-sql-driver/mysql"
	"github.com/google/uuid"
	"gorm.io/gorm"
)

// GroupRepo stores groups (teams) and their members.
type GroupRepo struct {
	g *gorm.DB
}

func NewGroupRepo(g *gorm.DB) *GroupRepo {
	return &GroupRepo{g: g}
}

func isDuplicateKey(err error) bool {
	var me *mysql.MySQLError
	return errors.As(err, &me) && me.Number == 1062
}

// List returns every group with its member count, ordered by name.
func (r *GroupRepo) List() ([]db.GroupSummary, error) {
	var groups []db.Group
	if err := r.g.Order("name ASC").Find(&groups).Error; err != nil {
		return nil, err
	}
	type countRow struct {
		GroupID string
		N       int64
	}
	var counts []countRow
	if err := r.g.Model(&db.GroupMember{}).
		Select("group_id, COUNT(*) AS n").
		Group("group_id").
		Scan(&counts).Error; err != nil {
		return nil, err
	}
	byGroup := make(map[string]int64, len(counts))
	for _, c := range counts {
		byGroup[c.GroupID] = c.N
	}
	out := make([]db.GroupSummary, 0, len(groups))
	for _, g := range groups {
		out = append(out, db.GroupSummary{Group: g, MemberCount: byGroup[g.ID]})
	}
	return out, nil
}

// Get returns one group and its members (joined with users, ordered by email).
func (r *GroupRepo) Get(id string) (*db.Group, []db.GroupMemberView, error) {
	var g db.Group
	if err := r.g.Where("id = ?", id).First(&g).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil, db.ErrGroupNotFound
		}
		return nil, nil, err
	}
	var members []db.GroupMemberView
	err := r.g.Table("user_group_members AS m").
		Select("m.user_email AS email, u.display_name AS display_name, " +
			"COALESCE(u.is_allowed, FALSE) AS is_allowed, m.added_by AS added_by, m.created_at AS added_at").
		Joins("LEFT JOIN users u ON u.email = m.user_email").
		Where("m.group_id = ?", id).
		Order("m.user_email ASC").
		Scan(&members).Error
	if err != nil {
		return nil, nil, err
	}
	return &g, members, nil
}

// Create inserts a group. Returns db.ErrGroupNameTaken on a duplicate name.
func (r *GroupRepo) Create(name, description, createdBy string) (*db.Group, error) {
	var n int64
	if err := r.g.Model(&db.Group{}).Where("name = ?", name).Count(&n).Error; err != nil {
		return nil, err
	}
	if n > 0 {
		return nil, db.ErrGroupNameTaken
	}
	g := db.Group{
		ID:          uuid.New().String(),
		Name:        name,
		Description: description,
		CreatedBy:   createdBy,
	}
	if err := r.g.Create(&g).Error; err != nil {
		if isDuplicateKey(err) {
			return nil, db.ErrGroupNameTaken
		}
		return nil, err
	}
	return &g, nil
}

// Update renames a group and/or changes its description.
func (r *GroupRepo) Update(id, name, description string) (*db.Group, error) {
	var g db.Group
	if err := r.g.Where("id = ?", id).First(&g).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, db.ErrGroupNotFound
		}
		return nil, err
	}
	if name != g.Name {
		var n int64
		if err := r.g.Model(&db.Group{}).Where("name = ? AND id <> ?", name, id).Count(&n).Error; err != nil {
			return nil, err
		}
		if n > 0 {
			return nil, db.ErrGroupNameTaken
		}
	}
	g.Name = name
	g.Description = description
	if err := r.g.Save(&g).Error; err != nil {
		if isDuplicateKey(err) {
			return nil, db.ErrGroupNameTaken
		}
		return nil, err
	}
	return &g, nil
}

// Delete removes a group and its memberships in one transaction.
func (r *GroupRepo) Delete(id string) error {
	return r.g.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("group_id = ?", id).Delete(&db.GroupMember{}).Error; err != nil {
			return err
		}
		res := tx.Where("id = ?", id).Delete(&db.Group{})
		if res.Error != nil {
			return res.Error
		}
		if res.RowsAffected == 0 {
			return db.ErrGroupNotFound
		}
		return nil
	})
}

// AddMember adds a known user to a group. Idempotent: adding an existing
// member is a no-op. The user must have logged in once (row in users).
func (r *GroupRepo) AddMember(groupID, email, addedBy string) error {
	email = strings.TrimSpace(email)
	var g db.Group
	if err := r.g.Where("id = ?", groupID).First(&g).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return db.ErrGroupNotFound
		}
		return err
	}
	var u db.User
	if err := r.g.Where("email = ?", email).First(&u).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return db.ErrUnknownUser
		}
		return err
	}
	m := db.GroupMember{GroupID: groupID, UserEmail: u.Email, AddedBy: addedBy, CreatedAt: time.Now()}
	if err := r.g.Create(&m).Error; err != nil {
		if isDuplicateKey(err) {
			return nil
		}
		return err
	}
	return nil
}

// RemoveMember removes a membership. Removing a non-member is a no-op.
func (r *GroupRepo) RemoveMember(groupID, email string) error {
	var n int64
	if err := r.g.Model(&db.Group{}).Where("id = ?", groupID).Count(&n).Error; err != nil {
		return err
	}
	if n == 0 {
		return db.ErrGroupNotFound
	}
	return r.g.Where("group_id = ? AND user_email = ?", groupID, strings.TrimSpace(email)).
		Delete(&db.GroupMember{}).Error
}

// Directory returns every user, every group and every membership, for
// internal consumers that resolve team permissions on their side.
func (r *GroupRepo) Directory() ([]db.User, []db.Group, []db.GroupMember, error) {
	var users []db.User
	if err := r.g.Order("email ASC").Find(&users).Error; err != nil {
		return nil, nil, nil, err
	}
	var groups []db.Group
	if err := r.g.Order("name ASC").Find(&groups).Error; err != nil {
		return nil, nil, nil, err
	}
	var members []db.GroupMember
	if err := r.g.Order("group_id ASC, user_email ASC").Find(&members).Error; err != nil {
		return nil, nil, nil, err
	}
	return users, groups, members, nil
}
