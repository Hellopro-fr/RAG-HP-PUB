import { ArrowRight } from 'lucide-react';
import type { TextBlockData } from '@/types/blocks/text';

interface TextBlockProps {
  data: TextBlockData;
}

/**
 * Bloc texte WYSIWYG.
 * Le HTML est rendu via dangerouslySetInnerHTML — il doit être
 * assaini côté serveur (DOMPurify) avant d'arriver ici.
 */
export function TextBlock({ data }: TextBlockProps) {
  return (
    <div className="my-4">
      {data.estimation && (
        <div className="mb-3 inline-flex items-baseline gap-2 rounded-md bg-primary-soft px-3 py-2">
          {data.estimation.label && (
            <span className="text-xs font-semibold uppercase tracking-wide text-primary">
              {data.estimation.label}
            </span>
          )}
          <span className="text-lg font-extrabold text-primary">{data.estimation.value}</span>
        </div>
      )}

      <div
        className="prose prose-sm max-w-none text-base leading-relaxed text-foreground/90"
        dangerouslySetInnerHTML={{ __html: data.html }}
      />

      {data.hasCta && (
        <button className="mt-4 inline-flex items-center gap-2 rounded-md bg-cta px-5 py-2.5 text-sm font-bold uppercase tracking-wide text-cta-foreground hover:bg-cta-hover">
          Demander un devis <ArrowRight className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
