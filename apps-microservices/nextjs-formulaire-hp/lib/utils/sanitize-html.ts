import DOMPurify from 'isomorphic-dompurify';

/**
 * Sanitize HTML content to prevent XSS attacks
 * Uses DOMPurify with a strict configuration
 */
export function sanitizeHtml(html: string | undefined | null): string {
  if (!html) return '';

  return DOMPurify.sanitize(html, {
    // Allowed tags for product descriptions
    ALLOWED_TAGS: [
      'p', 'br', 'b', 'i', 'strong', 'em', 'u', 's',
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'ul', 'ol', 'li',
      'a', 'span', 'div',
      'table', 'thead', 'tbody', 'tr', 'th', 'td',
      'blockquote', 'pre', 'code',
    ],
    // Allowed attributes
    ALLOWED_ATTR: [
      'href', 'target', 'rel', 'class', 'style',
      'colspan', 'rowspan',
    ],
    // Force all links to open in new tab with security attributes
    ADD_ATTR: ['target', 'rel'],
    // Remove potentially dangerous protocols
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i,
  });
}
