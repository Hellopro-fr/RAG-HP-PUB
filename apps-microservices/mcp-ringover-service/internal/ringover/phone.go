package ringover

import (
	"strconv"
	"strings"
)

// NormalizePhoneNumber converts a human-entered phone number to Ringover's
// filter format: an E.164 number WITHOUT the leading '+', as an int64
// (e.g. "+33 6 11 35 24 93" -> 33611352493). defaultCC is the country code
// (digits only, e.g. "33") prepended to national-format numbers.
//
// Returns (0, false) when the input is empty or cannot be parsed to a
// plausible number; callers then skip phone filtering rather than error.
func NormalizePhoneNumber(raw, defaultCC string) (int64, bool) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return 0, false
	}
	hasPlus := strings.HasPrefix(raw, "+")

	var b strings.Builder
	for _, r := range raw {
		if r >= '0' && r <= '9' {
			b.WriteRune(r)
		}
	}
	digits := b.String()
	if digits == "" {
		return 0, false
	}

	switch {
	case hasPlus:
		// "+33..." — digits already include the country code.
	case strings.HasPrefix(digits, "00"):
		// International prefix "0033..." -> "33...".
		digits = strings.TrimPrefix(digits, "00")
	case strings.HasPrefix(digits, "0"):
		// National with trunk 0 "06..." -> defaultCC + "6...".
		digits = defaultCC + digits[1:]
	case !strings.HasPrefix(digits, defaultCC):
		// Bare national number, no country code, no trunk 0
		// (e.g. "611352493") -> defaultCC + digits.
		digits = defaultCC + digits
	}
	// else: no '+', no leading 0, already starts with defaultCC -> assume
	// already E.164 (e.g. "33611352493"). Accepted ambiguity per the spec.

	if len(digits) < 8 { // E.164 numbers are at least ~8 digits.
		return 0, false
	}
	n, err := strconv.ParseInt(digits, 10, 64)
	if err != nil {
		return 0, false
	}
	return n, true
}
