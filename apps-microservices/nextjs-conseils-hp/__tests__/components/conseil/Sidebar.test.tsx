import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Sidebar } from '@/components/conseil/Sidebar';

const items = [
  { id: 'section-1', label: 'Introduction' },
  { id: 'section-2', label: 'Comparatif des solutions' },
  { id: 'section-3', label: 'Conclusion' },
];

describe('Sidebar', () => {
  it('renders nothing when items list is empty', () => {
    const { container } = render(<Sidebar items={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the "Sommaire" heading', () => {
    render(<Sidebar items={items} />);
    expect(screen.getByText('Sommaire')).toBeDefined();
  });

  it('renders all item labels', () => {
    render(<Sidebar items={items} />);
    items.forEach((item) => {
      expect(screen.getByText(item.label)).toBeDefined();
    });
  });

  it('generates correct anchor hrefs', () => {
    const { container } = render(<Sidebar items={items} />);
    const links = container.querySelectorAll('a');
    expect(links[0].getAttribute('href')).toBe('#section-1');
    expect(links[1].getAttribute('href')).toBe('#section-2');
  });

  it('renders zero-padded item numbers', () => {
    render(<Sidebar items={items} />);
    expect(screen.getByText('01')).toBeDefined();
    expect(screen.getByText('03')).toBeDefined();
  });
});
