import { describe, it, expect } from 'vitest';
import type { ImageImageBlockData, ImageItem } from '@/types/blocks/image-image';

describe('ImageImageBlockData', () => {
  it('accepts images without optional fields', () => {
    const data: ImageImageBlockData = {
      left: { src: '/img/left.jpg', alt: 'Image gauche' },
      right: { src: '/img/right.jpg', alt: 'Image droite' },
    };
    expect(data.left.src).toBe('/img/left.jpg');
    expect(data.right.src).toBe('/img/right.jpg');
  });

  it('ImageItem accepts width and height', () => {
    const item: ImageItem = {
      src: '/img/test.jpg',
      alt: 'Test',
      width: 640,
      height: 480,
    };
    expect(item.width).toBe(640);
    expect(item.height).toBe(480);
  });

  it('ImageItem width and height are optional', () => {
    const item: ImageItem = { src: '/img/test.jpg', alt: 'Test' };
    expect(item.width).toBeUndefined();
    expect(item.height).toBeUndefined();
  });
});
