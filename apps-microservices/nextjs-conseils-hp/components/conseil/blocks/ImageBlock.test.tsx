import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ImageBlock } from './ImageBlock';

vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: { src: string; alt: string; [k: string]: unknown }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} {...props} />
  ),
}));

describe('ImageBlock', () => {
  it('affiche l\'image avec le bon alt', () => {
    render(<ImageBlock data={{ src: 'https://cdn.hellopro.fr/img.jpg', alt: 'Bâtiment élevage' }} />);
    expect(screen.getByAltText('Bâtiment élevage')).toBeDefined();
  });

  it('affiche la légende quand présente', () => {
    render(<ImageBlock data={{ src: 'https://cdn.hellopro.fr/img.jpg', alt: 'img', caption: 'Vue d\'ensemble' }} />);
    expect(screen.getByText('Vue d\'ensemble')).toBeDefined();
  });

  it('ne rend pas de légende quand absente', () => {
    const { container } = render(<ImageBlock data={{ src: 'https://cdn.hellopro.fr/img.jpg', alt: 'img' }} />);
    expect(container.querySelector('figcaption')).toBeNull();
  });
});
