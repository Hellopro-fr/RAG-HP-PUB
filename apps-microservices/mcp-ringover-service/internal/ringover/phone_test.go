package ringover

import "testing"

func TestNormalizePhoneNumber(t *testing.T) {
	cases := []struct {
		name      string
		raw       string
		defaultCC string
		want      int64
		wantOK    bool
	}{
		{"national no trunk zero", "611352493", "33", 33611352493, true},
		{"national with trunk zero", "0611352493", "33", 33611352493, true},
		{"international plus spaced", "+33 6 11 35 24 93", "33", 33611352493, true},
		{"double zero prefix", "0033611352493", "33", 33611352493, true},
		{"already e164", "33611352493", "33", 33611352493, true},
		{"dashes and trunk zero", "06-11-35-24-93", "33", 33611352493, true},
		{"non-default country", "0611352493", "1", 1611352493, true},
		{"empty", "", "33", 0, false},
		{"letters only", "abc", "33", 0, false},
		{"too short after cc", "12", "33", 0, false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, ok := NormalizePhoneNumber(c.raw, c.defaultCC)
			if got != c.want || ok != c.wantOK {
				t.Errorf("NormalizePhoneNumber(%q, %q) = (%d, %v), want (%d, %v)",
					c.raw, c.defaultCC, got, ok, c.want, c.wantOK)
			}
		})
	}
}
