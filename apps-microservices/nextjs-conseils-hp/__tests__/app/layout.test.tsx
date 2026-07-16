import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import RootLayout from '@/app/layout';

describe('RootLayout', () => {
  it('renders children inside the body', () => {
    render(
      <RootLayout head={null}>
        <div data-testid="child">Content</div>
      </RootLayout>
    );
    expect(screen.getByTestId('child')).toBeDefined();
  });

  it('renders the head slot when provided', () => {
    render(
      <RootLayout head={<script type="application/ld+json" data-testid="schema">{'{}'}</script>}>
        <div>Content</div>
      </RootLayout>
    );
    // Le head slot est rendu dans <head> — hors du body — donc on cherche dans document
    expect(document.querySelector('[data-testid="schema"]')).toBeTruthy();
  });

  it('renders without head slot when null', () => {
    expect(() =>
      render(
        <RootLayout head={null}>
          <div>Content</div>
        </RootLayout>
      )
    ).not.toThrow();
  });
});
