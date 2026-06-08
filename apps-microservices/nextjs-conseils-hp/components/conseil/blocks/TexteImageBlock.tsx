import Image from 'next/image';
import { ArrowRight } from 'lucide-react';
import type { TexteImageBlockData } from '@/types/blocks/texte-image';

interface TexteImageBlockProps {
  data: TexteImageBlockData;
}

export function TexteImageBlock({ data }: TexteImageBlockProps) {
  // Blocs 4 & 5 : dimensions naturelles sans +9px (min-height commenté côté PHP)
  const w = data.image.width ?? 600;
  const h = data.image.height ?? 400;

  const imageCol = (
    <figure className="flex flex-col items-center">
      <div className="overflow-hidden rounded-xl">
        <Image
          src={data.image.src}
          alt={data.image.alt}
          width={w}
          height={h}
          className="h-auto max-w-full"
        />
      </div>
    </figure>
  );

  const textCol = (
    <div className="flex flex-col justify-center gap-3">
      {data.estimate && (
        <div className="inline-flex items-baseline gap-2 self-start rounded-md bg-primary-soft px-3 py-2">
          {data.estimateLabel && (
            <span className="text-xs font-semibold uppercase tracking-wide text-primary">
              {data.estimateLabel}
            </span>
          )}
          <span className="text-lg font-extrabold text-primary">{data.estimate}</span>
        </div>
      )}
      <div
        className="text-base leading-relaxed text-foreground/90
          [&_p]:mb-3 [&_p:last-child]:mb-0
          [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-1
          [&_ol]:list-decimal [&_ol]:pl-5
          [&_li]:mb-1
          [&_strong]:font-bold [&_b]:font-bold"
        dangerouslySetInnerHTML={{ __html: data.html }}
      />
      {data.ctaLabel && (
        <button className="mt-2 inline-flex items-center gap-2 self-start rounded-md bg-cta px-5 py-2.5 text-sm font-bold uppercase tracking-wide text-cta-foreground hover:bg-cta-hover">
          {data.ctaLabel} <ArrowRight className="h-4 w-4" />
        </button>
      )}
    </div>
  );

  return (
    <div className="my-8 grid gap-8 md:grid-cols-2 md:items-center">
      {data.imagePosition === 'left' ? (
        <>{imageCol}{textCol}</>
      ) : (
        <>{textCol}{imageCol}</>
      )}
    </div>
  );
}
