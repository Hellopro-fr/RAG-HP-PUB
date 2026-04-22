import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind class names with deduplication of conflicts.
 * Used by every shadcn/ui primitive.
 */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
