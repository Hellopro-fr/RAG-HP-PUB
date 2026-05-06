// v-safe-html: drop-in replacement for v-html that strips XSS vectors before
// assigning innerHTML. Uses the browser's native DOMParser + a tag/attribute
// allowlist. Use anywhere the bound HTML comes from the API or any
// user-influenced source. Static SVG snippets baked into a .vue template can
// still use v-html.
//
// To swap to DOMPurify later: `npm install dompurify`, replace sanitizeHtml
// implementation with a one-liner `DOMPurify.sanitize(input)`. The directive
// surface stays the same.
import type { Directive, DirectiveBinding } from 'vue'

// Allowed tags for rich-text content (admin-authored docs, BDD descriptions,
// LLM instructions). Mirrors a conservative subset of DOMPurify's defaults.
const ALLOWED_TAGS = new Set([
  'a', 'b', 'blockquote', 'br', 'code', 'div', 'em', 'h1', 'h2', 'h3', 'h4',
  'h5', 'h6', 'hr', 'i', 'img', 'li', 'ol', 'p', 'pre', 'span', 'strong',
  's', 'small', 'sub', 'sup', 'table', 'tbody', 'td', 'th', 'thead', 'tr',
  'u', 'ul',
])

// Per-tag attribute allowlist. Anything not listed gets dropped.
const ALLOWED_ATTRS: Record<string, Set<string>> = {
  a: new Set(['href', 'title', 'target', 'rel']),
  img: new Set(['src', 'alt', 'title', 'width', 'height']),
  '*': new Set(['class', 'id', 'style']),
}

// Reject any href/src that isn't a safe scheme. Blocks `javascript:`, `data:`,
// `vbscript:`. Allows http(s), mailto, tel, fragment, and same-origin paths.
const SAFE_URL = /^(?:https?:|mailto:|tel:|#|\/|\.\/|\.\.\/)/i

function sanitizeNode(node: Element): void {
  const tag = node.tagName.toLowerCase()

  // Strip the whole node if its tag isn't allowed.
  if (!ALLOWED_TAGS.has(tag)) {
    node.replaceWith(...Array.from(node.childNodes))
    return
  }

  // Strip disallowed attributes.
  const allowedForTag = ALLOWED_ATTRS[tag] ?? new Set<string>()
  const allowedGlobal = ALLOWED_ATTRS['*'] ?? new Set<string>()
  for (const attr of Array.from(node.attributes)) {
    const name = attr.name.toLowerCase()
    const ok = allowedForTag.has(name) || allowedGlobal.has(name)
    if (!ok) {
      node.removeAttribute(attr.name)
      continue
    }
    // Validate URL-bearing attrs.
    if ((name === 'href' || name === 'src') && !SAFE_URL.test(attr.value.trim())) {
      node.removeAttribute(attr.name)
      continue
    }
    // Strip on* event handlers defensively (shouldn't be in allowlist anyway).
    if (name.startsWith('on')) {
      node.removeAttribute(attr.name)
    }
  }

  // Recurse into children (snapshot first — replaceWith mutates the live list).
  for (const child of Array.from(node.children)) {
    sanitizeNode(child)
  }
}

export function sanitizeHtml(input: string): string {
  if (!input) return ''
  const doc = new DOMParser().parseFromString(`<div>${input}</div>`, 'text/html')
  const root = doc.body.firstElementChild
  if (!root) return ''
  for (const child of Array.from(root.children)) {
    sanitizeNode(child)
  }
  return root.innerHTML
}

function render(el: HTMLElement, binding: DirectiveBinding<unknown>): void {
  const raw = binding.value
  if (raw === null || raw === undefined || raw === '') {
    el.innerHTML = ''
    return
  }
  el.innerHTML = sanitizeHtml(String(raw))
}

export const safeHtml: Directive<HTMLElement, unknown> = {
  mounted: render,
  updated: render,
}
