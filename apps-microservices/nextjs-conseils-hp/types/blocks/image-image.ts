export interface ImageItem {
  src: string;
  alt: string;
  caption?: string;
  width?: number;
  height?: number;
}

export interface ImageImageBlockData {
  left: ImageItem;
  right: ImageItem;
}
