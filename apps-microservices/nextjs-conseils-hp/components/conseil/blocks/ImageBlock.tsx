import Image from 'next/image';
import type { ImageBlockData } from '@/types/blocks/image';

interface ImageBlockProps {
  data: ImageBlockData;
}

export function ImageBlock({ data }: ImageBlockProps) {
  const w = data.width ?? 800;
  const h = data.height ?? 450;

  return (
    <figure className="my-6">
      <div className="overflow-hidden rounded-xl">
        <Image
          src={data.src}
          alt={data.alt}
          width={w}
          height={h}
          className="h-auto w-full object-cover"
        />
      </div>
      {data.caption && (
        <figcaption className="mt-2 text-center text-sm text-muted-foreground">
          {data.caption}
        </figcaption>
      )}
    </figure>
  );
}
