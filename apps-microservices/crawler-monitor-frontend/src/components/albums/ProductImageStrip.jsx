import { ImageThumb } from './ImageThumb';

/**
 * Strip horizontale d'images d'un produit. Scroll horizontal si la bande
 * dépasse la largeur de la carte. Click sur une vignette → `onSelectImage(img)`
 * (le parent ProductCard ré-injectera le `product` avant de remonter).
 */
export function ProductImageStrip({ domain, images, onSelectImage }) {
  if (!images || images.length === 0) {
    return <div className="text-xs italic text-muted-foreground">Aucune image</div>;
  }
  return (
    <div className="flex gap-2 overflow-x-auto pt-1">
      {images.map((img) => (
        <ImageThumb
          key={img.filename}
          image={img}
          domain={domain}
          onClick={() => onSelectImage(img)}
        />
      ))}
    </div>
  );
}
