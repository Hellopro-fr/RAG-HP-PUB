package password

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"strings"

	"golang.org/x/crypto/bcrypt"
	"golang.org/x/crypto/scrypt"
)

const (
	prefix   = "scrypt"
	defaultN = 16384
	defaultR = 8
	defaultP = 1
	keyLen   = 64
	saltLen  = 16
)

// Hash produces a scrypt hash for new passwords.
func Hash(plain string) (string, error) {
	if plain == "" {
		return "", errors.New("password must be non-empty string")
	}
	salt := make([]byte, saltLen)
	if _, err := rand.Read(salt); err != nil {
		return "", err
	}
	derived, err := scrypt.Key([]byte(plain), salt, defaultN, defaultR, defaultP, keyLen)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%s$%d$%d$%d$%s$%s",
		prefix, defaultN, defaultR, defaultP,
		hex.EncodeToString(salt), hex.EncodeToString(derived)), nil
}

// Verify checks plain against hash. Supports both scrypt (new) and bcrypt (legacy Node.js) formats.
func Verify(plain, hash string) (bool, error) {
	if plain == "" || hash == "" {
		return false, nil
	}
	// bcrypt hashes start with $2b$ or $2a$ or $2y$ (Node.js bcrypt format)
	if strings.HasPrefix(hash, "$2") {
		err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(plain))
		if err == bcrypt.ErrMismatchedHashAndPassword {
			return false, nil
		}
		return err == nil, err
	}
	// scrypt format: scrypt$N$r$p$saltHex$derivedHex
	parts := strings.Split(hash, "$")
	if len(parts) != 6 || parts[0] != prefix {
		return false, nil
	}
	n, err1 := strconv.Atoi(parts[1])
	r, err2 := strconv.Atoi(parts[2])
	p, err3 := strconv.Atoi(parts[3])
	if err1 != nil || err2 != nil || err3 != nil {
		return false, nil
	}
	salt, err := hex.DecodeString(parts[4])
	if err != nil {
		return false, nil
	}
	expected, err := hex.DecodeString(parts[5])
	if err != nil || len(expected) == 0 {
		return false, nil
	}
	candidate, err := scrypt.Key([]byte(plain), salt, n, r, p, len(expected))
	if err != nil {
		return false, nil
	}
	return subtle.ConstantTimeCompare(candidate, expected) == 1, nil
}

// LooksLikeScryptHash returns true if the hash is in scrypt format.
func LooksLikeScryptHash(s string) bool {
	if !strings.HasPrefix(s, prefix+"$") {
		return false
	}
	return len(strings.Split(s, "$")) == 6
}
