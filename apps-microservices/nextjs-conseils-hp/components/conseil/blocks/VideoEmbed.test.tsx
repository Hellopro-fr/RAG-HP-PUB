import { describe, it, expect, vi, beforeAll } from 'vitest';
import { render } from '@testing-library/react';
import { VideoEmbed } from './VideoEmbed';

beforeAll(() => {
  const mockObserver = { observe: vi.fn(), disconnect: vi.fn() };
  vi.stubGlobal('IntersectionObserver', vi.fn(() => mockObserver));
});

describe('VideoEmbed', () => {
  it('rend un élément vidéo', () => {
    const { container } = render(
      <VideoEmbed
        placeholder="https://www.hellopro.fr/images/annuaire_hp/video-mockup.jpg"
        embedUrl="https://www.youtube.com/embed/dQw4w9WgXcQ"
        rawUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
      />
    );
    expect(container.firstChild).toBeTruthy();
  });
});
