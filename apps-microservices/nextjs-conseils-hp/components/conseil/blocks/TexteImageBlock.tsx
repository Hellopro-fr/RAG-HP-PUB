import Image from 'next/image';
import type { TexteImageBlockData } from '@/types/blocks/texte-image';
import { EstimationBox } from './EstimationBox';
import { TexteImageCta } from './TexteImageCta';

interface TexteImageBlockProps {
  data: TexteImageBlockData;
}

export function TexteImageBlock({ data }: TexteImageBlockProps) {
  // Blocs 4 & 5 : dimensions naturelles sans +9px (min-height commenté côté PHP)
  const hasDims = data.image.width !== undefined && data.image.height !== undefined;
  const w = data.image.width ?? 600;
  const h = data.image.height ?? 400;

  // Sans taille connue : unoptimized + width:auto → rendu à dimensions naturelles,
  // jamais d'upscale depuis une source plus petite que le fallback 600px.
  const imageEl = hasDims ? (
    <Image
      src={data.image.src}
      alt={data.image.alt}
      width={w}
      height={h}
      className="h-auto max-w-full"
      style={{ maxWidth: `${w}px` }}
      sizes={`(max-width: 768px) 100vw, ${w}px`}
    />
  ) : (
    <Image
      src={data.image.src}
      alt={data.image.alt}
      width={600}
      height={400}
      unoptimized
      className="h-auto max-w-full"
      style={{ width: 'auto', height: 'auto' }}
    />
  );

  const imageColAlign = data.imagePosition === 'left' ? 'md:items-start' : 'md:items-end';
  const imageCol = (
    <figure className={`flex min-w-0 flex-col items-center ${imageColAlign}`}>
      <div className="w-fit max-w-full overflow-hidden rounded-xl">
        {imageEl}
      </div>
    </figure>
  );

  const textCol = (
    <div className="flex min-w-0 flex-col gap-3">
      {data.estimate && (
        <EstimationBox
          label={data.estimateLabel ?? 'Estimation de prix'}
          value={data.estimate}
          className="not-prose"
          labelWidthClass="sm:w-[40%]"
        />
      )}
      <div
        className="text-base leading-relaxed text-foreground/90
          [&_p]:mb-3 [&_p:last-child]:mb-0
          [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-1
          [&_ol]:list-decimal [&_ol]:pl-5
          [&_li]:mb-1
          [&_strong]:font-bold [&_b]:font-bold
          [&_a]:text-primary [&_a]:underline [&_a:hover]:text-primary/80"
        dangerouslySetInnerHTML={{ __html: data.html }}
      />
      {data.ctaLabel && <TexteImageCta ctaUrl={data.ctaUrl} ctaLabel={data.ctaLabel} />}
    </div>
  );

  // Image 40% / Texte 60% — règle PHP flex-basis: 40% sur la colonne image
  const gridCols = data.imagePosition === 'left'
    ? 'md:grid-cols-[2fr_3fr]'
    : 'md:grid-cols-[3fr_2fr]';

  return (
    <div className={`my-8 grid gap-8 md:items-start ${gridCols}`}>
      {data.imagePosition === 'left' ? (
        <>{imageCol}{textCol}</>
      ) : (
        <>{textCol}{imageCol}</>
      )}
    </div>
  );
}
