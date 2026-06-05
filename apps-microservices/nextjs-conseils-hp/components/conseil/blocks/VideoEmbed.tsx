'use client';

import { useEffect, useRef } from 'react';

interface VideoEmbedProps {
  placeholder: string;
  embedUrl: string;
  rawUrl: string;
}

export function VideoEmbed({ placeholder, embedUrl, rawUrl }: VideoEmbedProps) {
  const ref = useRef<HTMLEmbedElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        el.src = embedUrl;
        el.classList.remove('lazy-load-img');
        observer.disconnect();
      },
      { rootMargin: '200px' },
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [embedUrl]);

  return (
    <embed
      ref={ref}
      src={placeholder}
      data-src={embedUrl}
      data-val={rawUrl}
      className="video-embed lazy-load-img w-[675px] h-[450px]"
    />
  );
}
