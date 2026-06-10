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
    <div className="relative w-full aspect-video overflow-hidden rounded-lg md:w-[675px] md:h-[450px]">
      <embed
        ref={ref}
        src={placeholder}
        data-src={embedUrl}
        data-val={rawUrl}
        className="video-embed lazy-load-img absolute inset-0 w-full h-full"
      />
    </div>
  );
}
