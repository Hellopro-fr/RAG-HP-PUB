import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ConseilTemplate } from '@/components/conseil/ConseilTemplate';
import { mockPagePrix } from '@/data/mocks/page-prix';
import type { AoFormQuestion } from '@/types/conseils';

// Isolation des composants lourds (header/footer/hero/sidebar non testés ici)
vi.mock('@/components/conseil/SiteHeader', () => ({ SiteHeader: () => <header data-testid="site-header" /> }));
vi.mock('@/components/conseil/SiteFooter', () => ({ SiteFooter: () => <footer data-testid="site-footer" /> }));
vi.mock('@/components/conseil/Hero', () => ({
  Hero: ({ data }: { data: { title: string } }) => <div data-testid="hero">{data.title}</div>,
}));
vi.mock('@/components/conseil/Sidebar', () => ({ Sidebar: () => <nav data-testid="sidebar" /> }));
vi.mock('@/components/conseil/BlockRenderer', () => ({ BlockRenderer: () => <div data-testid="block" /> }));
vi.mock('@/components/conseil/AuthorBlock', () => ({ AuthorBlock: () => <div data-testid="author" /> }));
vi.mock('@/components/conseil/Crossell', () => ({ Crossell: () => <div data-testid="crossell" /> }));
vi.mock('@/components/conseil/Suppliers', () => ({ Suppliers: () => <div data-testid="suppliers" /> }));
vi.mock('@/components/conseil/HeroQuoteForm', () => ({
  HeroQuoteForm: ({ question }: { question?: AoFormQuestion | null }) => (
    <div data-testid="hero-quote-form" data-question={question?.question ?? 'none'} />
  ),
}));

describe('ConseilTemplate', () => {
  it('renders main structural elements', () => {
    render(<ConseilTemplate page={mockPagePrix} />);
    expect(screen.getByTestId('site-header')).toBeDefined();
    expect(screen.getByTestId('site-footer')).toBeDefined();
    expect(screen.getByTestId('hero')).toBeDefined();
  });

  it('passes formulaire_ao to HeroQuoteForm', () => {
    const question: AoFormQuestion = {
      id: 1,
      question: 'Quel est votre projet ?',
      avecImage: false,
      choix: [{ id: 1, label: 'Option A' }],
    };
    const page = { ...mockPagePrix, formulaire_ao: question };
    render(<ConseilTemplate page={page} />);
    const form = screen.getByTestId('hero-quote-form');
    expect(form.getAttribute('data-question')).toBe('Quel est votre projet ?');
  });

  it('passes null formulaire_ao when absent', () => {
    const page = { ...mockPagePrix, formulaire_ao: undefined };
    render(<ConseilTemplate page={page} />);
    const form = screen.getByTestId('hero-quote-form');
    expect(form.getAttribute('data-question')).toBe('none');
  });
});
