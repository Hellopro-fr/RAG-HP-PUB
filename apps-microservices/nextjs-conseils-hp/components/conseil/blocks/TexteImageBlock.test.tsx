import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TexteImageBlock } from './TexteImageBlock';
import type { TexteImageBlockData } from '@/types/blocks/texte-image';

vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: { src: string; alt: string; [k: string]: unknown }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} {...props} />
  ),
}));

const BASE: TexteImageBlockData = {
  html: '<p>Texte du bloc</p>',
  image: { src: 'https://cdn.hellopro.fr/img.jpg', alt: 'Photo chantier' },
  imagePosition: 'right',
};

describe('TexteImageBlock', () => {
  it('affiche le texte HTML', () => {
    render(<TexteImageBlock data={BASE} />);
    expect(screen.getByText('Texte du bloc')).toBeDefined();
  });

  it('affiche l\'image avec le bon alt', () => {
    render(<TexteImageBlock data={BASE} />);
    expect(screen.getByAltText('Photo chantier')).toBeDefined();
  });

  it('affiche le badge estimation quand présent', () => {
    render(<TexteImageBlock data={{ ...BASE, estimate: '200 €', estimateLabel: 'Estimation' }} />);
    expect(screen.getByText('200 €')).toBeDefined();
  });

  it('fonctionne avec imagePosition left (type 5)', () => {
    const { container } = render(<TexteImageBlock data={{ ...BASE, imagePosition: 'left' }} />);
    expect(container.querySelector('figure')).toBeTruthy();
  });

  it('affiche l\'image avec dimensions connues (taille définie)', () => {
    render(<TexteImageBlock data={{ ...BASE, image: { ...BASE.image, width: 400, height: 300 } }} />);
    expect(screen.getByAltText('Photo chantier')).toBeDefined();
  });
});
