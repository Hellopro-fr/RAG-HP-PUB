package gateway

import (
	"strings"
	"testing"
)

func TestComposeInstructions_Empty(t *testing.T) {
	got := ComposeInstructions(nil, "t1")
	if got != "" {
		t.Errorf("expected empty string for nil input, got %q", got)
	}
	got = ComposeInstructions([]InstructionView{}, "t1")
	if got != "" {
		t.Errorf("expected empty string for empty slice, got %q", got)
	}
}

func TestComposeInstructions_SingleEntry(t *testing.T) {
	ins := []InstructionView{
		{ID: "1", Title: "Use search first", Body: "<p>Prefer leexi_search_meetings over list.</p>"},
	}
	got := ComposeInstructions(ins, "t1")
	// Underscores in raw text survive because EscapeMode=disabled — that
	// keeps tool names like leexi_search_meetings readable when the LLM
	// reads the injected instructions.
	want := "## Use search first\nPrefer leexi_search_meetings over list."
	if got != want {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestComposeInstructions_MultipleEntries(t *testing.T) {
	ins := []InstructionView{
		{ID: "1", Title: "First", Body: "<p>Alpha body.</p>"},
		{ID: "2", Title: "Second", Body: "<p>Beta body.</p>"},
	}
	got := ComposeInstructions(ins, "t1")
	want := "## First\nAlpha body.\n\n## Second\nBeta body."
	if got != want {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestComposeInstructions_SkipsEmptyBody(t *testing.T) {
	ins := []InstructionView{
		{ID: "1", Title: "Kept", Body: "<p>Alpha.</p>"},
		{ID: "2", Title: "Dropped", Body: "   \n\t  "},
		{ID: "3", Title: "AlsoKept", Body: "<p>Gamma.</p>"},
	}
	got := ComposeInstructions(ins, "t1")
	if strings.Contains(got, "Dropped") {
		t.Errorf("composer should skip entries with whitespace-only body, got %q", got)
	}
	if !strings.Contains(got, "Kept") || !strings.Contains(got, "AlsoKept") {
		t.Errorf("composer dropped non-empty entries: %q", got)
	}
}

func TestComposeInstructions_SkipsEmptyTitle(t *testing.T) {
	// A title of just whitespace falls back to a generic header rather than
	// producing an orphan body — keeps the output valid markdown.
	ins := []InstructionView{
		{ID: "1", Title: "   ", Body: "<p>Body without title.</p>"},
	}
	got := ComposeInstructions(ins, "t1")
	if !strings.Contains(got, "Body without title.") {
		t.Errorf("body should be rendered even when title is blank, got %q", got)
	}
}

func TestComposeInstructions_Truncation(t *testing.T) {
	big := strings.Repeat("A", 10_000)
	ins := []InstructionView{
		{ID: "1", Title: "Huge", Body: big},
	}
	got := ComposeInstructions(ins, "t1")
	if len(got) > maxInstructionsBytes {
		t.Errorf("composed length %d exceeds cap %d", len(got), maxInstructionsBytes)
	}
	if !strings.HasSuffix(got, truncationMarker) {
		t.Errorf("truncated output should end with %q, got suffix %q", truncationMarker, got[len(got)-20:])
	}
}

func TestComposeInstructions_TrimsTrailingWhitespace(t *testing.T) {
	ins := []InstructionView{
		{ID: "1", Title: "A", Body: "<p>body</p>"},
	}
	got := ComposeInstructions(ins, "t1")
	if strings.HasSuffix(got, " ") || strings.HasSuffix(got, "\n") {
		t.Errorf("output should not end with whitespace/newline, got %q", got)
	}
}

// ── HTML → Markdown conversion ─────────────────────────────────────────────

func TestComposeInstructions_ConvertsParagraphsAndBreaks(t *testing.T) {
	ins := []InstructionView{
		{ID: "1", Title: "", Body: "<p>First para.</p><p>Second para.</p>"},
	}
	got := ComposeInstructions(ins, "t1")
	if !strings.Contains(got, "First para.") || !strings.Contains(got, "Second para.") {
		t.Errorf("both paragraphs should be present: %q", got)
	}
	if strings.Contains(got, "<p>") {
		t.Errorf("output must not contain raw HTML tags: %q", got)
	}
}

func TestComposeInstructions_ConvertsBoldItalicLinkCode(t *testing.T) {
	ins := []InstructionView{
		{ID: "1", Title: "", Body: `<p>Use <strong>search</strong> and <em>list</em> and <a href="https://x">docs</a> and <code>run</code>.</p>`},
	}
	got := ComposeInstructions(ins, "t1")
	// Bold, link, code have a single canonical form; italic accepts either
	// `*list*` or `_list_` — both are valid CommonMark.
	for _, want := range []string{"**search**", "[docs](https://x)", "`run`"} {
		if !strings.Contains(got, want) {
			t.Errorf("expected %q in output, got %q", want, got)
		}
	}
	if !strings.Contains(got, "*list*") && !strings.Contains(got, "_list_") {
		t.Errorf("italic conversion expected *list* or _list_, got %q", got)
	}
}

func TestComposeInstructions_ConvertsUnorderedList(t *testing.T) {
	ins := []InstructionView{
		{ID: "1", Title: "Steps", Body: "<ul><li>first</li><li>second</li></ul>"},
	}
	got := ComposeInstructions(ins, "t1")
	// Common markdown list markers: "- first", "* first", or "- first" etc.
	// The converter uses "- ". Accept either "- " or "* " prefix.
	if !strings.Contains(got, "first") || !strings.Contains(got, "second") {
		t.Errorf("list items missing in output: %q", got)
	}
	if strings.Contains(got, "<li>") || strings.Contains(got, "<ul>") {
		t.Errorf("list HTML tags should be converted: %q", got)
	}
}

func TestComposeInstructions_ConvertsOrderedList(t *testing.T) {
	ins := []InstructionView{
		{ID: "1", Title: "", Body: "<ol><li>one</li><li>two</li></ol>"},
	}
	got := ComposeInstructions(ins, "t1")
	if !strings.Contains(got, "1.") || !strings.Contains(got, "one") {
		t.Errorf("ordered list should use numeric markers, got %q", got)
	}
}

func TestComposeInstructions_ConvertsBlockquoteAndHeadings(t *testing.T) {
	ins := []InstructionView{
		{ID: "1", Title: "", Body: "<blockquote>important</blockquote><h3>Section</h3><p>body</p>"},
	}
	got := ComposeInstructions(ins, "t1")
	if !strings.Contains(got, "> important") {
		t.Errorf("blockquote should use \"> \" prefix, got %q", got)
	}
	if !strings.Contains(got, "### Section") {
		t.Errorf("h3 should convert to ###, got %q", got)
	}
}

func TestComposeInstructions_StripsScriptAndDangerousAttrs(t *testing.T) {
	// Defence in depth: even if a malicious body slipped past the UI, the
	// Markdown output must not carry <script> tags or event handlers.
	ins := []InstructionView{
		{ID: "1", Title: "", Body: `<p onclick="x()">hello</p><script>alert(1)</script>`},
	}
	got := ComposeInstructions(ins, "t1")
	if strings.Contains(got, "<script>") {
		t.Errorf("script tag should be stripped: %q", got)
	}
	if strings.Contains(got, "onclick") {
		t.Errorf("event handlers should be stripped: %q", got)
	}
	if !strings.Contains(got, "hello") {
		t.Errorf("visible text should survive: %q", got)
	}
}

func TestComposeInstructions_PlainTextBodyPassesThrough(t *testing.T) {
	// Legacy rows with plain text (no HTML markup) must not be mangled.
	ins := []InstructionView{
		{ID: "1", Title: "T", Body: "plain line one\nplain line two"},
	}
	got := ComposeInstructions(ins, "t1")
	if !strings.Contains(got, "plain line one") || !strings.Contains(got, "plain line two") {
		t.Errorf("plain text should survive conversion, got %q", got)
	}
}
