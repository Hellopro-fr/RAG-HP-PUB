package gateway

import (
	"log"
	"regexp"
	"strings"
	"sync"

	md "github.com/JohannesKaufmann/html-to-markdown"
	"github.com/JohannesKaufmann/html-to-markdown/plugin"
)

// htmlTagPattern detects whether a body contains HTML markup. If it doesn't,
// we skip the converter entirely to avoid escaping markdown-special chars
// ("_", "*", etc.) inside plain-text legacy content.
var htmlTagPattern = regexp.MustCompile(`<[a-zA-Z/!][^>]*>`)

// InstructionView is the runtime snapshot of an LLMInstruction carried inside
// a scope token or OAuth2 client's cached entry. Only the fields the composer
// needs are included — callers resolve and filter by allowed servers before
// constructing the slice. Body is stored as WYSIWYG HTML; the composer
// converts it to Markdown before concatenation so the LLM receives a clean,
// well-formed Markdown document.
type InstructionView struct {
	ID    string
	Title string
	Body  string
}

// maxInstructionsBytes caps the composed instructions string so a misconfigured
// giant body can't blow up every `initialize` response. 8 KiB is far beyond any
// reasonable system-prompt addition; hosts that inject this into their prompt
// already budget for it.
const maxInstructionsBytes = 8192

const truncationMarker = "\n\n[…truncated]"

// converter is reused across calls — construction walks the plugin registry
// and allocates regex machinery we don't want to repeat per `initialize`.
// Wrapped in sync.Once because config.Converter is not documented as safe
// for concurrent init but is safe for concurrent Convert calls.
var (
	converterOnce sync.Once
	converter     *md.Converter
)

func getConverter() *md.Converter {
	converterOnce.Do(func() {
		// EscapeMode "disabled" leaves raw "_" and "*" alone. The WYSIWYG
		// always emits explicit tags (<strong>, <em>, <code>…), so any loose
		// punctuation in text is meant literally — keeping `search_meetings`
		// readable in the LLM prompt matters more than a pedantic
		// round-trip-to-HTML guarantee.
		opts := &md.Options{EscapeMode: "disabled"}
		c := md.NewConverter("", true, opts)
		// GitHubFlavored adds strikethrough, tables, task lists, auto-links —
		// matches what the TipTap WYSIWYG emits and what most modern
		// LLM-facing tools already understand.
		c.Use(plugin.GitHubFlavored())
		converter = c
	})
	return converter
}

// htmlToMarkdown converts a single WYSIWYG HTML fragment to GitHub-Flavored
// Markdown. Inputs without any HTML tags are returned verbatim (trimmed) so
// plain-text legacy bodies don't get their underscores / asterisks escaped.
// On conversion failure falls back to the raw input so a malformed row never
// silently disappears.
func htmlToMarkdown(html string) string {
	html = strings.TrimSpace(html)
	if html == "" {
		return ""
	}
	if !htmlTagPattern.MatchString(html) {
		return html
	}
	out, err := getConverter().ConvertString(html)
	if err != nil {
		log.Printf("[gateway] html-to-markdown conversion failed: %v (falling back to raw html)", err)
		return html
	}
	return strings.TrimSpace(out)
}

// ComposeInstructions renders the given instructions as flat
// "## <title>\n<body-as-markdown>" blocks joined by "\n\n". Bodies are
// converted from the WYSIWYG HTML stored in the DB to Markdown so the full
// payload is a valid Markdown document the LLM can parse structurally.
// Whitespace-only bodies are skipped entirely. The scopeLabel is logged on
// truncation so operators can identify which token / client is generating
// oversized output.
func ComposeInstructions(instructions []InstructionView, scopeLabel string) string {
	if len(instructions) == 0 {
		return ""
	}

	blocks := make([]string, 0, len(instructions))
	for _, ins := range instructions {
		body := htmlToMarkdown(ins.Body)
		if body == "" {
			continue
		}
		title := strings.TrimSpace(ins.Title)
		var block string
		if title == "" {
			block = body
		} else {
			block = "## " + title + "\n" + body
		}
		blocks = append(blocks, block)
	}

	if len(blocks) == 0 {
		return ""
	}

	out := strings.TrimRightFunc(strings.Join(blocks, "\n\n"), func(r rune) bool {
		return r == ' ' || r == '\n' || r == '\t' || r == '\r'
	})

	if len(out) > maxInstructionsBytes {
		log.Printf("[gateway] llm instructions truncated for scope=%q: %d → %d bytes",
			scopeLabel, len(out), maxInstructionsBytes)
		cut := maxInstructionsBytes - len(truncationMarker)
		if cut < 0 {
			cut = 0
		}
		out = out[:cut] + truncationMarker
	}

	return out
}
