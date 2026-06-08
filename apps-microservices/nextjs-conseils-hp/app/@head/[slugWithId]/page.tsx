import { fetchConseilPage } from '@/lib/api/conseils';

type Props = {
  params: Promise<{ slugWithId: string }>;
};

function parseId(slugWithId: string): number | null {
  const match = slugWithId.match(/^.+-(\d+)(?:\.html)?$/);
  return match ? Number(match[1]) : null;
}

export default async function HeadSlot({ params }: Props) {
  const { slugWithId } = await params;
  const id = parseId(slugWithId);
  if (!id) return null;

  const result = await fetchConseilPage(id);
  if (!result.ok) return null;
  const page = result.page;
  if (!page.schemaGuide && !page.schemaBreadcrumb) return null;

  return (
    <>
      {page.schemaGuide && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(page.schemaGuide) }}
        />
      )}
      {page.schemaBreadcrumb && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(page.schemaBreadcrumb) }}
        />
      )}
    </>
  );
}
