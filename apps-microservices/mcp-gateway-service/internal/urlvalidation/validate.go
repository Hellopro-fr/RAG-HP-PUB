package urlvalidation

import (
	"fmt"
	"net"
	"net/url"
	"strings"
)

// ValidateServerURL checks that a URL is safe to use as a backend MCP server.
// It blocks private/loopback/link-local/metadata IP ranges to prevent SSRF.
func ValidateServerURL(rawURL string) error {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return fmt.Errorf("invalid URL: %w", err)
	}

	// Enforce http or https scheme only
	scheme := strings.ToLower(parsed.Scheme)
	if scheme != "http" && scheme != "https" {
		return fmt.Errorf("unsupported scheme %q: only http and https are allowed", parsed.Scheme)
	}

	hostname := parsed.Hostname()
	if hostname == "" {
		return fmt.Errorf("URL must have a hostname")
	}

	// Resolve hostname to IPs and check each one
	ips, err := net.LookupHost(hostname)
	if err != nil {
		// If DNS resolution fails, still check if the hostname itself is an IP literal
		if ip := net.ParseIP(hostname); ip != nil {
			if isBlockedIP(ip) {
				return fmt.Errorf("URL resolves to a blocked IP range: %s", ip)
			}
			return nil
		}
		return fmt.Errorf("cannot resolve hostname %q: %w", hostname, err)
	}

	for _, ipStr := range ips {
		ip := net.ParseIP(ipStr)
		if ip != nil && isBlockedIP(ip) {
			return fmt.Errorf("URL resolves to a blocked IP range: %s", ipStr)
		}
	}

	return nil
}

// isBlockedIP returns true if the IP is in a private, loopback, link-local,
// or cloud metadata range that should not be accessed by the gateway.
func isBlockedIP(ip net.IP) bool {
	// Loopback (127.0.0.0/8, ::1)
	if ip.IsLoopback() {
		return true
	}
	// Private (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, fc00::/7)
	if ip.IsPrivate() {
		return true
	}
	// Link-local (169.254.0.0/16, fe80::/10)
	if ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() {
		return true
	}
	// Unspecified (0.0.0.0, ::)
	if ip.IsUnspecified() {
		return true
	}

	// Cloud metadata endpoints (169.254.169.254 is already covered by link-local,
	// but explicitly block the GCP/AWS metadata range for clarity)
	metadataCIDRs := []string{
		"169.254.169.254/32", // AWS/GCP/Azure metadata
		"100.100.100.200/32", // Alibaba Cloud metadata
	}
	for _, cidr := range metadataCIDRs {
		_, network, _ := net.ParseCIDR(cidr)
		if network != nil && network.Contains(ip) {
			return true
		}
	}

	return false
}
