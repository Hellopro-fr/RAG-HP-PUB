'use client';

import { useEffect, useState } from 'react';
import { HubIcon } from './primitives';
import type { HubNavItem } from '@/types/hub';

/**
 * Sommaire horizontal collant, avec suivi de la section active.
 *
 * Tous les liens sont de vraies ancres `<a href="#id">` rendues en SSR : le
 * JavaScript n'ajoute que le surlignage de la section courante et le défilement
 * doux. Sans JS, la navigation fonctionne quand même — et Googlebot voit les
 * 8 liens internes.
 *
 * Une entrée dont la cible n'existe pas dans le DOM est retirée au montage :
 * mieux vaut un sommaire plus court qu'un lien qui ne mène nulle part (cas des
 * sections encore absentes ou d'une page HUB qui n'a pas tous les blocs).
 */
const SCROLL_OFFSET = 96; // hauteur du header collant

export function HubSectionNav({ items }: { items: HubNavItem[] }) {
  const [visibleIds, setVisibleIds] = useState<string[] | null>(null);
  const [activeId, setActiveId] = useState<string>(items[0]?.id ?? '');

  // Filtre les ancres réellement présentes (après hydratation).
  useEffect(() => {
    setVisibleIds(items.filter((item) => document.getElementById(item.id)).map((i) => i.id));
  }, [items]);

  useEffect(() => {
    if (!visibleIds || visibleIds.length === 0) return;
    // Absent de jsdom et de quelques navigateurs anciens. Le sommaire reste
    // fonctionnel sans lui : seul le surlignage de la section active est perdu.
    if (typeof IntersectionObserver === 'undefined') return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]) setActiveId(visible[0].target.id);
      },
      { rootMargin: '-24% 0px -60% 0px', threshold: [0.15, 0.35, 0.6] }
    );

    for (const id of visibleIds) {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    }
    return () => observer.disconnect();
  }, [visibleIds]);

  const handleClick = (event: React.MouseEvent<HTMLAnchorElement>, id: string) => {
    const element = document.getElementById(id);
    if (!element) return; // laisse le navigateur gérer l'ancre
    event.preventDefault();
    window.scrollTo({
      top: element.getBoundingClientRect().top + window.scrollY - SCROLL_OFFSET,
      behavior: 'smooth',
    });
  };

  // Avant hydratation on rend tout : le HTML initial doit contenir les liens.
  const rendered = visibleIds ? items.filter((item) => visibleIds.includes(item.id)) : items;
  if (rendered.length === 0) return null;

  return (
    <nav
      aria-label="Sommaire de la page"
      className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur supports-[backdrop-filter]:bg-background/80"
    >
      <ul className="mx-auto flex max-w-7xl gap-2 overflow-x-auto px-4 py-2.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {rendered.map((item) => {
          const active = item.id === activeId;
          return (
            <li key={item.id}>
              <a
                href={`#${item.id}`}
                onClick={(event) => handleClick(event, item.id)}
                aria-current={active ? 'true' : undefined}
                className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm font-semibold transition ${
                  active
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                }`}
              >
                <HubIcon name={item.icon} className="h-4 w-4" />
                {item.label}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
