'use client';

/**
 * Effet « fête » (confettis) pour les écrans de remerciement du HUB.
 *
 * Purement CSS/déterministe : les pièces sont dérivées de leur index (aucun
 * `Math.random` → pas de mismatch d'hydratation) et l'animation est portée par un
 * keyframe injecté localement, pour ne pas toucher `globals.css`. Décoratif :
 * `pointer-events-none` + `aria-hidden`.
 */
const COLORS = [
  'var(--color-cta)',
  'var(--color-primary)',
  '#22c55e',
  '#eab308',
  '#ec4899',
];

const PIECES = Array.from({ length: 40 }, (_, i) => ({
  left: (i * 2.5 + (i % 5) * 1.3) % 100,
  delay: (i % 12) * 0.13,
  duration: 2.4 + (i % 6) * 0.22,
  color: COLORS[i % COLORS.length],
  rounded: i % 3 === 0,
  drift: (i % 2 === 0 ? 1 : -1) * (10 + (i % 5) * 8),
}));

export function Confetti() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <style>{`
        @keyframes hub-confetti-fall {
          0%   { transform: translateY(-10%) translateX(0) rotate(0deg); opacity: 0; }
          10%  { opacity: 1; }
          100% { transform: translateY(340px) translateX(var(--drift)) rotate(540deg); opacity: 0; }
        }
      `}</style>
      {PIECES.map((p, i) => (
        <span
          key={i}
          style={{
            position: 'absolute',
            top: 0,
            left: `${p.left}%`,
            width: 8,
            height: 8,
            backgroundColor: p.color,
            borderRadius: p.rounded ? '9999px' : '2px',
            // @ts-expect-error variable CSS custom
            '--drift': `${p.drift}px`,
            animation: `hub-confetti-fall ${p.duration}s ease-in ${p.delay}s 1 both`,
          }}
        />
      ))}
    </div>
  );
}
