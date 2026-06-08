import { describe, it, expect, vi } from 'vitest';

vi.mock('@/lib/api/conseils', () => ({
  fetchConseilPage: vi.fn().mockResolvedValue({
    ok: true,
    page: {
      schemaGuide: {
        '@context': 'http://schema.org',
        '@type': 'Guide',
        name: 'Test guide',
        author: 'Test Author',
        datePublished: '2026-01-01',
      },
    },
  }),
}));

describe('HeadSlot', () => {
  it('renders a script tag with JSON-LD when schemaGuide is present', async () => {
    const { default: HeadSlot } = await import('@/app/@head/[slugWithId]/page');
    const result = await HeadSlot({
      params: Promise.resolve({ slugWithId: 'test-guide-123' }),
    });
    expect(result).not.toBeNull();
  });

  it('returns null when the page is not found', async () => {
    const { fetchConseilPage } = await import('@/lib/api/conseils');
    vi.mocked(fetchConseilPage).mockResolvedValueOnce({ ok: false, reason: 'not-found' });

    const { default: HeadSlot } = await import('@/app/@head/[slugWithId]/page');
    const result = await HeadSlot({
      params: Promise.resolve({ slugWithId: 'test-guide-123' }),
    });
    expect(result).toBeNull();
  });

  it('returns null for an unparseable slug', async () => {
    const { default: HeadSlot } = await import('@/app/@head/[slugWithId]/page');
    const result = await HeadSlot({
      params: Promise.resolve({ slugWithId: 'invalid-slug' }),
    });
    expect(result).toBeNull();
  });
});
