import { z } from 'zod';

export const TypeSectionBlockDataSchema = z.object({
  id: z.string(),
  title: z.string(),
  estimate: z.string(),
  imageUrl: z.string().url(),
  imageAlt: z.string().optional(),
  descriptionHtml: z.string(), // HTML <p> sérialisé depuis le BO
  bullets: z.array(z.string()),
  ctaLabel: z.string().optional().default('Demander un devis'),
  ctaUrl: z.string().optional().default('#'),
});

export type TypeSectionBlockData = z.infer<typeof TypeSectionBlockDataSchema>;
