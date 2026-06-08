import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Suppliers } from '@/components/conseil/Suppliers';
import type { Supplier } from '@/types/conseils';

vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: { src: string; alt: string; [k: string]: unknown }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} {...props} />
  ),
}));

const MOCK_SUPPLIERS: Supplier[] = [
  { id: '3002237', name: 'TRANSFILOG', logoPath: 'https://www.hellopro.fr/images/logo/logo_3002237.jpg' },
  { id: '2195733', name: 'AZ MACHINERY', logoPath: 'https://www.hellopro.fr/images/logo/logo_2195733.jpg' },
];

describe('Suppliers', () => {
  it('affiche le nom de chaque fournisseur', () => {
    render(<Suppliers suppliers={MOCK_SUPPLIERS} />);
    expect(screen.getByText('TRANSFILOG')).toBeDefined();
    expect(screen.getByText('AZ MACHINERY')).toBeDefined();
  });

  it('affiche le logo quand logoPath est renseigné', () => {
    render(<Suppliers suppliers={MOCK_SUPPLIERS} />);
    const img = screen.getByAltText('Logo TRANSFILOG') as HTMLImageElement;
    expect(img.src).toContain('logo_3002237.jpg');
  });

  it('affiche une icône de remplacement si logoPath est vide', () => {
    render(<Suppliers suppliers={[{ id: '1', name: 'SANS LOGO', logoPath: '' }]} />);
    expect(screen.getByText('SANS LOGO')).toBeDefined();
  });

  it('ne rend rien si la liste est vide', () => {
    const { container } = render(<Suppliers suppliers={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('ne rend rien si suppliers est undefined', () => {
    const { container } = render(<Suppliers />);
    expect(container.firstChild).toBeNull();
  });

  it('compile les balises HTML de la description quand fournie par l\'API', () => {
    const supplier: Supplier = {
      id: '1', name: 'HTML CORP', logoPath: '',
      description: '<p>Société <strong>spécialisée</strong> en bâtiments.</p>',
    };
    render(<Suppliers suppliers={[supplier]} />);
    const strong = document.querySelector('strong');
    expect(strong?.textContent).toBe('spécialisée');
  });

  it('affiche le texte de secours si description absente', () => {
    render(<Suppliers suppliers={[{ id: '1', name: 'SANS DESC', logoPath: '' }]} />);
    expect(screen.getByText(/Fournisseur référencé sur HelloPro/)).toBeDefined();
  });

  it('affiche les flèches de navigation quand plus de 3 fournisseurs', () => {
    const many: Supplier[] = [
      { id: '1', name: 'A', logoPath: '' },
      { id: '2', name: 'B', logoPath: '' },
      { id: '3', name: 'C', logoPath: '' },
      { id: '4', name: 'D', logoPath: '' },
    ];
    render(<Suppliers suppliers={many} />);
    expect(screen.getByLabelText('Précédent')).toBeDefined();
    expect(screen.getByLabelText('Suivant')).toBeDefined();
  });

  it('n\'affiche pas les flèches pour 3 fournisseurs ou moins', () => {
    render(<Suppliers suppliers={MOCK_SUPPLIERS} />);
    expect(screen.queryByLabelText('Précédent')).toBeNull();
    expect(screen.queryByLabelText('Suivant')).toBeNull();
  });
});
