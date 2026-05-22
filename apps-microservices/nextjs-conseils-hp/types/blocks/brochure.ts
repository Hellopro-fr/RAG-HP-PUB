import { z } from 'zod';

export const BrochureBlockDataSchema = z.object({
  title: z.string(),
  description: z.string().optional(),
  bullets: z.array(z.string()),
  ctaLabel: z.string().optional().default('Recevoir le guide gratuit'),
});

export type BrochureBlockData = z.infer<typeof BrochureBlockDataSchema>;
