import { z } from 'zod';

export const QuoteFormBlockDataSchema = z.object({
  title: z.string().optional(),
  subtitle: z.string().optional(),
  ctaLabel: z.string().optional().default('Faire une demande groupée (1 min)'),
});

export type QuoteFormBlockData = z.infer<typeof QuoteFormBlockDataSchema>;
