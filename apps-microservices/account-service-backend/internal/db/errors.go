package db

import "errors"

// Sentinel errors shared by repositories and HTTP handlers, so handlers can
// map them to status codes without importing the repository package.
var (
	ErrGroupNotFound  = errors.New("group not found")
	ErrGroupNameTaken = errors.New("group name already in use")
	ErrUnknownUser    = errors.New("unknown user")
)
