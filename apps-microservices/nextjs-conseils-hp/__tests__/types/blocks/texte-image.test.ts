import { describe, it, expect } from 'vitest';
import type { TexteImageBlockData } from '@/types/blocks/texte-image';

describe('TexteImageBlockData', () => {
  it('accepts image without optional dimensions', () => {
    const data: TexteImageBlockData = {
      html: '<p>Texte</p>',
      image: { src: '/img.jpg', alt: 'Image' },
      imagePosition: 'right',
    };
    expect(data.image.width).toBeUndefined();
    expect(data.image.height).toBeUndefined();
  });

  it('accepts image with natural dimensions', () => {
    const data: TexteImageBlockData = {
      html: '<p>Texte</p>',
      image: { src: '/img.jpg', alt: 'Image', width: 480, height: 320 },
      imagePosition: 'left',
    };
    expect(data.image.width).toBe(480);
    expect(data.image.height).toBe(320);
  });

  it('imagePosition can be right or left', () => {
    const right: TexteImageBlockData = {
      html: '',
      image: { src: '/img.jpg', alt: '' },
      imagePosition: 'right',
    };
    const left: TexteImageBlockData = {
      html: '',
      image: { src: '/img.jpg', alt: '' },
      imagePosition: 'left',
    };
    expect(right.imagePosition).toBe('right');
    expect(left.imagePosition).toBe('left');
  });
});
