import Image from 'next/image';
import type { ImageImageBlockData, ImageItem } from '@/types/blocks/image-image';

function ImageCol({ img }: { img: ImageItem }) {
  const w = img.width ?? 600;
  // +9 px : règle héritée du template PHP (getimagesize + 9), appliquée en min-height
  const minH = (img.height ?? 400) + 9;

  return (
    <figure className="flex flex-col items-center">
      <div
        className="flex items-center justify-center overflow-hidden rounded-xl"
        style={{ minHeight: `${minH}px` }}
      >
        <Image
          src={img.src}
          alt={img.alt}
          width={w}
          height={minH}
          className="h-auto max-w-full"
        />
      </div>
      {img.caption && (
        <figcaption className="mt-2 text-center text-sm text-muted-foreground">
          {img.caption}
        </figcaption>
      )}
    </figure>
  );
}

export function ImageImageBlock({ data }: { data: ImageImageBlockData }) {
  return (
    <div className="my-8 grid gap-4 md:grid-cols-2">
      <ImageCol img={data.left} />
      <ImageCol img={data.right} />
    </div>
  );
}
