'use client';

import { RefObject, useEffect, useState } from 'react';

interface TableScrollNav {
  canScrollLeft: boolean;
  canScrollRight: boolean;
}

export function useTableScrollNav(ref: RefObject<HTMLElement | null>): TableScrollNav {
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const update = () => {
      const { scrollLeft, scrollWidth, clientWidth } = el;
      setCanScrollLeft(scrollLeft > 0);
      setCanScrollRight(scrollLeft + clientWidth < scrollWidth - 1);
    };

    update();
    el.addEventListener('scroll', update, { passive: true });

    const ro = new ResizeObserver(update);
    ro.observe(el);
    if (el.firstElementChild) ro.observe(el.firstElementChild);

    return () => {
      el.removeEventListener('scroll', update);
      ro.disconnect();
    };
  }, [ref]);

  return { canScrollLeft, canScrollRight };
}
