import type { VideoBlockData } from '@/types/blocks/video';
import { VideoEmbed } from './VideoEmbed';

const VIDEO_PLACEHOLDER = 'https://www.hellopro.fr/images/annuaire_hp/video-mockup.jpg';

function resolveYouTube(url: string): string | null {
  const match =
    url.match(/youtube\.com\/watch\?(?:.*&)?v=([^&]+)/) ||
    url.match(/youtu\.be\/([^?]+)/);
  return match ? `https://www.youtube.com/embed/${match[1]}` : null;
}

function resolveDailymotion(url: string): string | null {
  const match = url.match(/dailymotion\.com\/video\/([^?_]+)/);
  return match ? `https://dailymotion.com/embed/video/${match[1]}` : null;
}

async function resolveVimeo(url: string): Promise<string | null> {
  try {
    const apiUrl = `https://vimeo.com/api/oembed.json?url=${encodeURIComponent(url)}&width=640`;
    const res = await fetch(apiUrl, { next: { revalidate: 86400 } });
    if (!res.ok) return null;
    const data = (await res.json()) as { html: string };
    const match = data.html.match(/src="([^"]+)"/);
    return match ? match[1] : null;
  } catch {
    return null;
  }
}

async function resolveEmbedUrl(url: string): Promise<string | null> {
  if (url.includes('youtube.com') || url.includes('youtu.be')) return resolveYouTube(url);
  if (url.includes('dailymotion.com')) return resolveDailymotion(url);
  if (url.includes('vimeo.com')) return resolveVimeo(url);
  return null;
}

interface VideoBlockProps {
  data: VideoBlockData;
}

export async function VideoBlock({ data }: VideoBlockProps) {
  if (!data.url) return null;

  const embedUrl = await resolveEmbedUrl(data.url);
  if (!embedUrl) return null;

  return (
    <div className="my-6 flex flex-col items-center">
      {data.title && (
        <p className="mb-2 text-sm font-medium text-muted-foreground">{data.title}</p>
      )}
      <VideoEmbed placeholder={VIDEO_PLACEHOLDER} embedUrl={embedUrl} rawUrl={data.url} />
    </div>
  );
}
