import { describe, it, expect, vi, beforeEach, afterEach, beforeAll } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HeroQuoteForm } from '@/components/conseil/HeroQuoteForm';
import type { AoFormQuestion } from '@/types/conseils';

// Mock global pour tous les tests — HeroQuoteForm utilise IntersectionObserver dans son useEffect
beforeAll(() => {
  vi.stubGlobal('IntersectionObserver', vi.fn(() => ({ observe: vi.fn(), disconnect: vi.fn() })));
});

const mockQuestion: AoFormQuestion = {
  id: 42,
  question: 'Quel type de projet ?',
  avecImage: false,
  typeSelection: 1,
  obligatoire: 0,
  choix: [
    { id: 1, label: 'Construction neuve' },
    { id: 2, label: 'Rénovation' },
    { id: 3, label: 'Extension', image: 'https://www.hellopro.fr/img/extension.jpg' },
  ],
};

describe('HeroQuoteForm', () => {
  it('renders without question (fallback)', () => {
    render(<HeroQuoteForm />);
    expect(screen.getByText(/Quel est votre besoin/i)).toBeDefined();
    expect(screen.getByText(/3 devis gratuits/i)).toBeDefined();
  });

  it('displays the question from API', () => {
    render(<HeroQuoteForm question={mockQuestion} />);
    expect(screen.getByText('Quel type de projet ?')).toBeDefined();
  });

  it('renders all choices', () => {
    render(<HeroQuoteForm question={mockQuestion} />);
    expect(screen.getByText('Construction neuve')).toBeDefined();
    expect(screen.getByText('Rénovation')).toBeDefined();
    expect(screen.getByText('Extension')).toBeDefined();
  });

  it('renders image for choices that have one', () => {
    render(<HeroQuoteForm question={mockQuestion} />);
    const img = screen.getByAltText('Extension') as HTMLImageElement;
    expect(img.src).toContain('extension.jpg');
  });

  it('highlights selected choice on click', () => {
    render(<HeroQuoteForm question={mockQuestion} />);
    const btn = screen.getByText('Construction neuve').closest('button')!;
    fireEvent.click(btn);
    expect(btn.className).toContain('ring-2');
  });

  it('renders with null question (no choices shown)', () => {
    render(<HeroQuoteForm question={null} />);
    expect(screen.getByText(/Quel est votre besoin/i)).toBeDefined();
  });

  it('shows the CTA button', () => {
    render(<HeroQuoteForm question={mockQuestion} />);
    expect(screen.getByText(/demande groupée/i)).toBeDefined();
  });
});

describe('HeroQuoteForm — GTM quote_form_funnel', () => {
  let observerCallback: IntersectionObserverCallback;
  let mockObserver: { observe: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    (window as any).dataLayer = [{ product: { category5: 'Mon-guide-conseil' } }];
    mockObserver = { observe: vi.fn(), disconnect: vi.fn() };
    vi.stubGlobal(
      'IntersectionObserver',
      vi.fn((cb: IntersectionObserverCallback) => {
        observerCallback = cb;
        return mockObserver;
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete (window as any).dataLayer;
  });

  it('pousse quote_form_funnel quand le formulaire entre dans le viewport', () => {
    render(<HeroQuoteForm question={{ ...mockQuestion, stepNumber: 3 }} />);
    observerCallback([{ isIntersecting: true } as IntersectionObserverEntry], mockObserver as unknown as IntersectionObserver);

    const dl: any[] = (window as any).dataLayer;
    const push = dl.find((d: any) => d.event === 'quote_form_funnel');
    expect(push).toBeDefined();
    expect(push.step_index).toBe(0);
    expect(push.step_name).toBe('1ere-question');
    expect(push.step_number).toBe(3);
    expect(push.funnel_context).toBe('header pages conseils');
    expect(push.user_known_status).toBe('Unknown');
    expect(push['product.category5']).toBe('Mon-guide-conseil');
    expect(push.funnel_devisplus).toBe('True');
    expect(push.step_type).toBe('1ere-question');
    expect(push.page_location_uri).toBeDefined();
  });

  it('omet step_number si absent de l\'API', () => {
    render(<HeroQuoteForm question={mockQuestion} />);
    observerCallback([{ isIntersecting: true } as IntersectionObserverEntry], mockObserver as unknown as IntersectionObserver);

    const dl: any[] = (window as any).dataLayer;
    const push = dl.find((d: any) => d.event === 'quote_form_funnel');
    expect(push).toBeDefined();
    expect('step_number' in push).toBe(false);
  });

  it('ne pousse pas si le formulaire n\'entre pas dans le viewport', () => {
    render(<HeroQuoteForm question={mockQuestion} />);
    observerCallback([{ isIntersecting: false } as IntersectionObserverEntry], mockObserver as unknown as IntersectionObserver);

    const dl: any[] = (window as any).dataLayer;
    expect(dl.find((d: any) => d.event === 'quote_form_funnel')).toBeUndefined();
  });
});
