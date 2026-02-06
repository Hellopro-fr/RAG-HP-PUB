import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Configuration des URLs pour les assets statiques
 * - En local: utilise le chemin relatif avec basePath
 * - En production: utilise l'URL complète du domaine
 */
export const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';
export const assetBaseUrl = process.env.NEXT_PUBLIC_ASSET_BASE_URL || '';

export function getAssetPath(path: string): string {
  // Si le chemin est déjà absolu (http/https), ne pas modifier
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }

  // En production avec ASSET_BASE_URL défini, utiliser l'URL complète
  if (assetBaseUrl) {
    return `${assetBaseUrl}${basePath}${path}`;
  }

  // Sinon, utiliser le basePath relatif (dev local)
  return `${basePath}${path}`;
}
