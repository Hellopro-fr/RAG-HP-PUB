import { z } from 'zod';
import type { AoFormQuestion } from '@/types/conseils';

export const QuoteFormBlockDataSchema = z.object({
  title: z.string().optional(),
  subtitle: z.string().optional(),
  ctaLabel: z.string().optional(),
});

export type QuoteFormBlockData = z.infer<typeof QuoteFormBlockDataSchema> & {
  /** Question AO injectée depuis formulaire_ao — non stockée en BO */
  question?: AoFormQuestion;
};
