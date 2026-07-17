import type { H2BlockData } from '@/types/blocks/h2';

interface H2BlockProps {
  data: H2BlockData;
}

export function H2Block({ data }: H2BlockProps) {
  return (
    <section id={data.id} className="mt-12 scroll-mt-32">
      <h2 className="text-3xl font-extrabold text-foreground">{data.title}</h2>
      {data.intro && (
        <p className="mt-3 text-base leading-relaxed text-foreground/90">{data.intro}</p>
      )}
    </section>
  );
}
