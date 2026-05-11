import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Pill from '../src/components/ui/Pill';
import StatTile from '../src/components/ui/StatTile';
import Sparkline from '../src/components/ui/Sparkline';
import Timeline from '../src/components/ui/Timeline';
import CapacityRing from '../src/components/ui/CapacityRing';
import AreaChart from '../src/components/ui/AreaChart';
import LogLine from '../src/components/ui/LogLine';
import KV from '../src/components/ui/KV';

describe('Pill', () => {
  it('rend le texte enfant', () => {
    render(<Pill tone="ok">Actif</Pill>);
    expect(screen.getByText('Actif')).toBeTruthy();
  });
  it('rend le dot quand dot=true', () => {
    const { container } = render(<Pill tone="err" dot>Erreur</Pill>);
    expect(container.querySelector('.bg-err')).toBeTruthy();
  });
  it('applique tone neutral par défaut', () => {
    const { container } = render(<Pill>Test</Pill>);
    expect(container.querySelector('.bg-bg-2')).toBeTruthy();
  });
  it('ajoute animate-pulse-dot quand pulse=true', () => {
    const { container } = render(<Pill dot pulse tone="ok">Live</Pill>);
    expect(container.querySelector('.animate-pulse-dot')).toBeTruthy();
  });
});

describe('StatTile', () => {
  it('rend le skeleton quand value=null', () => {
    const { container } = render(<StatTile label="Total" value={null} />);
    expect(container.querySelector('.animate-shimmer')).toBeTruthy();
  });
  it('rend la valeur quand fournie', () => {
    render(<StatTile label="Total" value="1 234" />);
    expect(screen.getByText('1 234')).toBeTruthy();
  });
  it('rend le label', () => {
    render(<StatTile label="Succès" value="42" />);
    expect(screen.getByText('Succès')).toBeTruthy();
  });
  it('applique text-warn quand deltaTone="warn"', () => {
    const { container } = render(<StatTile label="KO" value="5" delta="+2" deltaTone="warn" />);
    expect(container.querySelector('.text-warn')).toBeTruthy();
  });
});

describe('Sparkline', () => {
  it('rend une ligne plate quand data=[]', () => {
    const { container } = render(<Sparkline data={[]} />);
    expect(container.querySelector('line')).toBeTruthy();
  });
  it('rend une polyline avec des données', () => {
    const { container } = render(<Sparkline data={[1, 2, 3, 2, 1]} />);
    expect(container.querySelector('polyline')).toBeTruthy();
  });
  it('rend une polyline sans NaN avec un seul point', () => {
    const { container } = render(<Sparkline data={[5]} />);
    const poly = container.querySelector('polyline');
    expect(poly).toBeTruthy();
    expect(poly.getAttribute('points')).not.toContain('NaN');
  });
});

describe('Timeline', () => {
  it('rend un shimmer quand data=[]', () => {
    const { container } = render(<Timeline data={[]} />);
    expect(container.querySelector('.animate-shimmer')).toBeTruthy();
  });
  it('rend les barres ok avec des données', () => {
    const { container } = render(
      <Timeline data={[{ label: '0h', ok: 5, run: 1, fail: 0 }]} />
    );
    expect(container.querySelector('.bg-ok')).toBeTruthy();
  });
});

describe('CapacityRing', () => {
  it('rend le pourcentage correct', () => {
    render(<CapacityRing used={7} total={10} />);
    expect(screen.getByText('70%')).toBeTruthy();
  });
  it('cap à 100%', () => {
    render(<CapacityRing used={15} total={10} />);
    expect(screen.getByText('100%')).toBeTruthy();
  });
  it('rend le label', () => {
    render(<CapacityRing used={5} total={10} label="RAM" />);
    expect(screen.getByText('RAM')).toBeTruthy();
  });
});

describe('AreaChart', () => {
  it('renders SVG with axes', () => {
    const { container } = render(<AreaChart data={[10, 20, 30]} />);
    expect(container.querySelector('svg')).toBeTruthy();
    const lines = container.querySelectorAll('line');
    expect(lines.length).toBeGreaterThanOrEqual(2);
  });
  it('renders empty state without crash', () => {
    const { container } = render(<AreaChart data={[]} />);
    expect(container.querySelector('svg')).toBeTruthy();
  });
  it('renders refLine when provided', () => {
    const { container } = render(<AreaChart data={[10, 20]} refLine={50} />);
    const lines = Array.from(container.querySelectorAll('line'));
    const dashed = lines.find(l => l.getAttribute('stroke-dasharray') || l.getAttribute('strokeDasharray'));
    expect(dashed).toBeTruthy();
  });
});

describe('LogLine', () => {
  it('renders message text', () => {
    render(<LogLine t="12:00" lvl="info" msg="test message" />);
    expect(screen.getByText('test message')).toBeTruthy();
  });
  it('applies err color for err level', () => {
    const { container } = render(<LogLine t="12:00" lvl="err" msg="oops" />);
    expect(container.querySelector('.text-err')).toBeTruthy();
  });
  it('renders meta when provided', () => {
    render(<LogLine t="12:00" lvl="warn" msg="warn msg" meta="req_id=abc" />);
    expect(screen.getByText('req_id=abc')).toBeTruthy();
  });
});

describe('KV', () => {
  it('renders key and value', () => {
    render(<KV k="Status" v="running" />);
    expect(screen.getByText('Status')).toBeTruthy();
    expect(screen.getByText('running')).toBeTruthy();
  });
  it('renders em dash for null value', () => {
    render(<KV k="RAM" v={null} />);
    expect(screen.getByText('—')).toBeTruthy();
  });
  it('applies mono class when mono=true', () => {
    const { container } = render(<KV k="ID" v="abc-123" mono />);
    expect(container.querySelector('.font-mono')).toBeTruthy();
  });
});
