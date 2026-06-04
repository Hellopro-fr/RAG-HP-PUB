import Image from 'next/image';
import type { ImageImageBlockData } from '@/types/blocks/image-image';

interface ImageImageBlockProps {
  data: ImageImageBlockData;
}

function ImageCol({ img }: { img: ImageImageBlockData['left'] }) {
  return (
    <figure>
      <div className="overflow-hidden rounded-xl">
        <Image
          src={img.src}
          alt={img.alt}
          width={600}
          height={400}
          className="h-auto w-full object-cover"
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

export function ImageImageBlock({ data }: ImageImageBlockProps) {
  return (
    <div className="my-8 grid gap-4 md:grid-cols-2">
      <ImageCol img={data.left} />
      <ImageCol img={data.right} />
    </div>
  );
}
