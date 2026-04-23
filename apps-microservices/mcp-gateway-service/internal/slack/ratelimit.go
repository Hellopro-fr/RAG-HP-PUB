package slack

import (
	"sync"
	"time"
)

// CooldownLimiter suppresses repeat events for the same key within a cooldown
// window. Used to keep noisy scanners from flooding the Slack channel with
// unauthorized-attempt alerts.
//
// A cooldown of 0 (or negative) disables the limiter — Allow always returns
// true. That lets callers configure "no rate limit" via SLACK_AUTH_ALERT_COOLDOWN=0
// without needing a separate flag.
type CooldownLimiter struct {
	cooldown time.Duration
	mu       sync.Mutex
	last     map[string]time.Time
}

func NewCooldownLimiter(cooldown time.Duration) *CooldownLimiter {
	return &CooldownLimiter{
		cooldown: cooldown,
		last:     make(map[string]time.Time),
	}
}

// Allow returns true when the key has not fired within the cooldown window,
// and records the time. Returns true immediately when cooldown <= 0.
func (l *CooldownLimiter) Allow(key string) bool {
	if l.cooldown <= 0 {
		return true
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	now := time.Now()
	if t, ok := l.last[key]; ok && now.Sub(t) < l.cooldown {
		return false
	}
	l.last[key] = now
	return true
}
