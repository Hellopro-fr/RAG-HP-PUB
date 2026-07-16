import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ImageImageBlock } from './ImageImageBlock';

vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: { src: string; alt: string; [k: string]: unknown }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} {...props} />
  ),
}));

const DATA = {
  left: { src: 'https://cdn.hellopro.fr/left.jpg', alt: 'Image gauche' },
  right: { src: 'https://cdn.hellopro.fr/right.jpg', alt: 'Image droite' },
};

describe('ImageImageBlock', () => {
  it('affiche les deux images', () => {
    render(<ImageImageBlock data={DATA} />);
    expect(screen.getByAltText('Image gauche')).toBeDefined();
    expect(screen.getByAltText('Image droite')).toBeDefined();
  });

  it('affiche les légendes quand présentes', () => {
    render(<ImageImageBlock data={{
      left: { ...DATA.left, caption: 'Légende gauche' },
      right: { ...DATA.right, caption: 'Légende droite' },
    }} />);
    expect(screen.getByText('Légende gauche')).toBeDefined();
    expect(screen.getByText('Légende droite')).toBeDefined();
  });
});
