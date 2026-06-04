import { Check, X } from 'lucide-react';
import type { ProsConsBlockData } from '@/types/blocks/pros-cons';

interface ProsConsBlockProps {
  data: ProsConsBlockData;
}

export function ProsConsBlock({ data }: ProsConsBlockProps) {
  return (
    <div className="not-prose my-8 grid gap-4 md:grid-cols-2">
      <div className="rounded-xl border border-success/30 bg-success/5 p-5">
        <h3 className="mb-3 flex items-center gap-2 text-base font-bold text-foreground">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-success text-success-foreground">
            <Check className="h-4 w-4" />
          </span>
          {data.labelPros ?? 'Avantages'}
        </h3>
        <ul className="space-y-2 text-sm text-foreground">
          {data.pros.map((p) => (
            <li key={p} className="flex gap-2">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />
              <span>{p}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-5">
        <h3 className="mb-3 flex items-center gap-2 text-base font-bold text-foreground">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-destructive text-destructive-foreground">
            <X className="h-4 w-4" />
          </span>
          {data.labelCons ?? 'Inconvénients'}
        </h3>
        <ul className="space-y-2 text-sm text-foreground">
          {data.cons.map((c) => (
            <li key={c} className="flex gap-2">
              <X className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
              <span>{c}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
