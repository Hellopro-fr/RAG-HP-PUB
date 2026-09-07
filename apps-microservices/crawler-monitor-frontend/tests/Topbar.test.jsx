import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from '../src/components/providers/ThemeProvider';
import { Topbar } from '../src/components/layout/Topbar';

/**
 * Badge de liaison temps reel : trois etats exclusifs, « Hors ligne » prioritaire
 * sur « Degrade ».
 */
function renderTopbar(props) {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={['/']}>
        <Topbar {...props} />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('Topbar — badge de sante', () => {
  it('affiche Live quand le WS est connecte et le backend sain', () => {
    renderTopbar({ wsConnected: true, health: { degraded: false } });
    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it('affiche Degrade avec le motif Redis quand redis_connected est false', () => {
    renderTopbar({ wsConnected: true, health: { degraded: true, redis_connected: false } });
    const badge = screen.getByText('Dégradé');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute('title', 'Redis injoignable');
  });

  it('affiche Degrade avec le motif flux inactif quand Redis repond', () => {
    renderTopbar({ wsConnected: true, health: { degraded: true, redis_connected: true } });
    expect(screen.getByText('Dégradé')).toHaveAttribute(
      'title',
      'Flux temps réel backend inactif depuis > 60 s',
    );
  });

  it('garde Hors ligne prioritaire sur Degrade quand le WS est coupe', () => {
    renderTopbar({ wsConnected: false, health: { degraded: true, redis_connected: false } });
    expect(screen.getByText('Hors ligne')).toBeInTheDocument();
    expect(screen.queryByText('Dégradé')).toBeNull();
  });
});
