package gateway

import (
	"log"
	"regexp"
	"strings"
	"sync"

	md "github.com/JohannesKaufmann/html-to-markdown"
	"github.com/JohannesKaufmann/html-to-markdown/plugin"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/mcp"
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
	// Kind mirrors db.LLMInstructionRow.Kind ("general" | "per_server").
	// Empty is treated as "general" so pre-upgrade callers keep rendering
	// everywhere. ServerIDs carries the per_server row's linked servers —
	// used only by DecorateToolsWithInstructions to route the row to the
	// owning server's tools.
	Kind      string
	ServerIDs []string
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

// HTMLToMarkdown converts a single WYSIWYG HTML fragment to GitHub-Flavored
// Markdown. Inputs without any HTML tags are returned verbatim (trimmed) so
// plain-text legacy bodies don't get their underscores / asterisks escaped.
// On conversion failure falls back to the raw input so a malformed row never
// silently disappears.
func HTMLToMarkdown(html string) string {
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
	out := composeBlocks(instructions)
	if out == "" {
		return ""
	}

	if len(out) > maxInstructionsBytes {
		log.Printf("[gateway] llm instructions truncated for scope=%q: %d → %d bytes",
			scopeLabel, len(out), maxInstructionsBytes)
		out = truncateWithMarker(out, maxInstructionsBytes)
	}

	return out
}

// composeBlocks renders instructions as "## <title>\n<body-as-markdown>"
// blocks joined by "\n\n", without any size cap. Shared by the initialize
// composer (8 KiB cap) and the tool-description decorator (per-tool cap).
func composeBlocks(instructions []InstructionView) string {
	if len(instructions) == 0 {
		return ""
	}

	blocks := make([]string, 0, len(instructions))
	for _, ins := range instructions {
		body := HTMLToMarkdown(ins.Body)
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

	return strings.TrimRightFunc(strings.Join(blocks, "\n\n"), func(r rune) bool {
		return r == ' ' || r == '\n' || r == '\t' || r == '\r'
	})
}

// truncateWithMarker cuts s to at most max bytes, ending with truncationMarker.
func truncateWithMarker(s string, max int) string {
	cut := max - len(truncationMarker)
	if cut < 0 {
		cut = 0
	}
	return s[:cut] + truncationMarker
}

// maxToolInstructionBytes caps the instruction suffix appended to a single
// tool description. Tool descriptions are sent for every tool on tools/list,
// so the budget is tighter than the initialize field's 8 KiB.
const maxToolInstructionBytes = 4096

// toolInstructionsHeader visually separates the original tool description
// from the appended instruction blocks.
const toolInstructionsHeader = "\n\n---\nServer instructions (apply when using this tool):\n\n"

// DecorateToolsWithInstructions appends instruction blocks to tool
// descriptions for MCP hosts that ignore the initialize `instructions`
// field. Routing: "general" rows (Kind empty or "general") are appended to
// EVERY tool; "per_server" rows only to tools owned by one of the row's
// linked servers, resolved through toolServerIDs (prefixed tool name →
// server ID). Tools absent from toolServerIDs get only general rows.
// The appended suffix is capped at maxToolInstructionBytes per tool.
// The input slice is modified in place and returned.
func DecorateToolsWithInstructions(tools []mcp.Tool, instructions []InstructionView, toolServerIDs map[string]string, scopeLabel string) []mcp.Tool {
	if len(tools) == 0 || len(instructions) == 0 {
		return tools
	}

	var general []InstructionView
	perServer := make(map[string][]InstructionView)
	for _, ins := range instructions {
		if ins.Kind == db.LLMInstructionRowKindPerServer {
			for _, sid := range ins.ServerIDs {
				perServer[sid] = append(perServer[sid], ins)
			}
			continue
		}
		general = append(general, ins)
	}

	// Pre-compose each distinct suffix once — the general block is shared by
	// every tool and per-server blocks by every tool of that server.
	suffixCache := make(map[string]string)
	suffixFor := func(serverID string) string {
		if s, ok := suffixCache[serverID]; ok {
			return s
		}
		matching := append(append([]InstructionView{}, general...), perServer[serverID]...)
		composed := composeBlocks(matching)
		var suffix string
		if composed != "" {
			suffix = toolInstructionsHeader + composed
			if len(suffix) > maxToolInstructionBytes {
				log.Printf("[gateway] tool-description instructions truncated for scope=%q server=%q: %d → %d bytes",
					scopeLabel, serverID, len(suffix), maxToolInstructionBytes)
				suffix = truncateWithMarker(suffix, maxToolInstructionBytes)
			}
		}
		suffixCache[serverID] = suffix
		return suffix
	}

	for i := range tools {
		// Unknown tools (empty serverID) share the "" cache slot → general rows only.
		if suffix := suffixFor(toolServerIDs[tools[i].Name]); suffix != "" {
			tools[i].Description += suffix
		}
	}
	return tools
}
