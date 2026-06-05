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
        className="text-base leading-relaxed text-foreground/90
          [&_p]:mb-3 [&_p:last-child]:mb-0
          [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-1 [&_ul]:mb-3
          [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:space-y-1 [&_ol]:mb-3
          [&_li]:mb-1
          [&_strong]:font-bold [&_b]:font-bold
          [&_em]:italic [&_i]:italic
          [&_a]:text-primary [&_a]:underline [&_a:hover]:text-primary/80"
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
