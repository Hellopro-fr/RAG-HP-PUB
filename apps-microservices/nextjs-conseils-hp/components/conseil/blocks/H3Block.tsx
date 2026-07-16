import type { H3BlockData } from '@/types/blocks/h3';

interface H3BlockProps {
  data: H3BlockData;
}

export function H3Block({ data }: H3BlockProps) {
  return (
    <h3 className="mt-8 border-l-[3px] border-primary pl-3 text-2xl font-extrabold text-foreground">{data.title}</h3>
  );
}
