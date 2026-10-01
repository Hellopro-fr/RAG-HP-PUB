import { describe, it, expect } from 'vitest';
import { sanitizeHubHtml } from '@/lib/hub/sanitize';

/**
 * Le sanitizer est écrit à la main (voir le commentaire du module : DOMPurify
 * embarque jsdom et casse le build Docker). Il mérite donc une couverture serrée.
 *
 * Propriété centrale : AUCUN attribut n'est conservé, jamais. Les balises
 * autorisées sont reconstruites depuis leur seul nom.
 */
describe('sanitizeHubHtml', () => {
  it('conserve les balises d’emphase autorisées', () => {
    expect(sanitizeHubHtml('Apport de <strong>20 %</strong>.')).toBe(
      'Apport de <strong>20 %</strong>.'
    );
    expect(sanitizeHubHtml('<em>a</em><b>b</b><i>c</i>')).toBe('<em>a</em><b>b</b><i>c</i>');
  });

  it('conserve les listes et paragraphes', () => {
    expect(sanitizeHubHtml('<ul><li>Un</li><li>Deux</li></ul>')).toBe(
      '<ul><li>Un</li><li>Deux</li></ul>'
    );
    expect(sanitizeHubHtml('<p>Texte</p>')).toBe('<p>Texte</p>');
  });

  it('normalise <br> en auto-fermante', () => {
    expect(sanitizeHubHtml('a<br>b')).toBe('a<br />b');
    expect(sanitizeHubHtml('a<br/>b')).toBe('a<br />b');
  });

  it('supprime les scripts AVEC leur contenu', () => {
    expect(sanitizeHubHtml('Avant<script>alert(1)</script>Après')).toBe('AvantAprès');
  });

  it('supprime style, iframe, object, embed, template, noscript avec leur contenu', () => {
    expect(sanitizeHubHtml('<style>body{}</style>x')).toBe('x');
    expect(sanitizeHubHtml('<iframe src="//evil"></iframe>x')).toBe('x');
    expect(sanitizeHubHtml('<object data="x"></object>y')).toBe('y');
    expect(sanitizeHubHtml('<template><b>z</b></template>w')).toBe('w');
  });

  it('retire TOUS les attributs des balises autorisées', () => {
    expect(sanitizeHubHtml('<span class="x" style="color:red" onclick="e()">t</span>')).toBe(
      '<span>t</span>'
    );
    expect(sanitizeHubHtml('<strong data-x="1">t</strong>')).toBe('<strong>t</strong>');
  });

  it('retire les balises non autorisées en gardant leur texte', () => {
    expect(sanitizeHubHtml('<a href="//evil">lien</a>')).toBe('lien');
    expect(sanitizeHubHtml('<div><h2>Titre</h2></div>')).toBe('Titre');
  });

  it('neutralise un vecteur onerror', () => {
    const out = sanitizeHubHtml('<img src=x onerror="alert(1)">');
    expect(out).not.toContain('onerror');
    expect(out).not.toContain('<img');
  });

  it('supprime les commentaires HTML', () => {
    expect(sanitizeHubHtml('a<!-- <script>alert(1)</script> -->b')).toBe('ab');
  });

  it('neutralise un script non fermé (texte visible, rien d’exécutable)', () => {
    // La balise ouvrante n'étant pas dans l'allowlist, elle est retirée ; il ne
    // reste que du texte inerte.
    const out = sanitizeHubHtml('<script>alert(1)');
    expect(out).toBe('alert(1)');
    expect(out).not.toContain('<script');
  });

  it('gère la casse et les espaces dans les balises', () => {
    expect(sanitizeHubHtml('<STRONG >t</STRONG >')).toBe('<strong>t</strong>');
    expect(sanitizeHubHtml('<SCRIPT>x</SCRIPT>y')).toBe('y');
  });

  it('laisse le texte simple intact', () => {
    expect(sanitizeHubHtml('Aucune balise ici.')).toBe('Aucune balise ici.');
    expect(sanitizeHubHtml('')).toBe('');
  });
});
