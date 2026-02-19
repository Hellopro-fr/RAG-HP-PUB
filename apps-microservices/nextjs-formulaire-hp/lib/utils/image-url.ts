/**
 * Utilitaires pour les URLs d'images produit
 *
 * Les images sont servies via un proxy interne pour cacher la structure des chemins.
 * Le chemin original est encodé en Base64 URL-safe.
 */

import { basePath } from '@/lib/utils';

/**
 * Encode un chemin d'image en Base64 URL-safe
 * @param imagePath - Chemin retourné par l'API (ex: "www.site.com/produit-2/6/9/8/file.jpg")
 * @returns Chemin encodé pour l'URL publique
 */
export function encodeImagePath(imagePath: string): string {
  // Encode en Base64
  const base64 = btoa(imagePath);
  // Convertit en Base64 URL-safe (remplace + par -, / par _, supprime =)
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/**
 * Décode un chemin d'image depuis Base64 URL-safe
 * @param encodedPath - Chemin encodé
 * @returns Chemin original
 */
export function decodeImagePath(encodedPath: string): string {
  // Reconvertit depuis Base64 URL-safe
  let base64 = encodedPath.replace(/-/g, '+').replace(/_/g, '/');
  // Ajoute le padding si nécessaire
  while (base64.length % 4) {
    base64 += '=';
  }
  return atob(base64);
}

/**
 * Génère l'URL publique pour une image produit
 * @param imagePath - Chemin retourné par l'API (ex: "www.site.com/produit-2/6/9/8/file.jpg")
 * @returns URL complète pour afficher l'image (ex: "/formulaire/api/images/d3d3LnNpdGU...")
 */
export function getProductImageUrl(imagePath: string): string {
  if (!imagePath) return '';
  const encoded = encodeImagePath(imagePath);
  const apiBase = basePath || '';
  return `${apiBase}/api/images/${encoded}`;
}

/**
 * Génère les URLs publiques pour un tableau d'images
 * @param imagePaths - Tableau de chemins d'images
 * @returns Tableau d'URLs publiques
 */
export function getProductImageUrls(imagePaths: string[]): string[] {
  if (!imagePaths || !Array.isArray(imagePaths)) return [];
  return imagePaths.map(getProductImageUrl).filter(Boolean);
}
