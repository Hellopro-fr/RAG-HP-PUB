import Image from 'next/image';
import type { ImageBlockData } from '@/types/blocks/image';

interface ImageBlockProps {
  data: ImageBlockData;
}

export function ImageBlock({ data }: ImageBlockProps) {
  const w = data.width ?? 800;
  // +9 px : règle héritée du template PHP (getimagesize + 9)
  const h = (data.height ?? 450) + 9;

  return (
    <figure className="my-6 flex flex-col items-center">
      <div className="overflow-hidden rounded-xl">
        <Image
          src={data.src}
          alt={data.alt}
          width={w}
          height={h}
          className="h-auto max-w-full"
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
