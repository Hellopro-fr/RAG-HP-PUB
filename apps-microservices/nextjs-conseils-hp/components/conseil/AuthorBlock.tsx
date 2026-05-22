import Image from 'next/image';
import { Linkedin, Mail } from 'lucide-react';

export interface AuthorData {
  name: string;
  role: string;
  bio: string;
  photo?: string;
  linkedinUrl?: string;
  contactEmail?: string;
}

interface AuthorBlockProps {
  author: AuthorData;
}

/**
 * Bloc auteur — affiché en pied d'article sur les 3 types de pages.
 * Composant serveur.
 */
export function AuthorBlock({ author }: AuthorBlockProps) {
  return (
    <section
      id="author"
      className="not-prose my-12 scroll-mt-32 rounded-2xl border border-border bg-gradient-to-br from-primary-soft to-card p-6 shadow-sm"
    >
      <div className="flex flex-col items-center gap-5 text-center sm:flex-row sm:text-left">
        {author.photo ? (
          <Image
            src={author.photo}
            alt={author.name}
            width={96}
            height={96}
            className="h-24 w-24 shrink-0 rounded-full border-4 border-card object-cover shadow-lg"
          />
        ) : (
          <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-full border-4 border-card bg-primary-soft text-3xl font-extrabold text-primary shadow-lg">
            {author.name.charAt(0)}
          </div>
        )}

        <div className="flex-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-cta">
            Guide écrit par
          </span>
          <h3 className="text-xl font-extrabold text-foreground">
            {author.name} · {author.role}
          </h3>
          <p className="mt-2 text-sm text-foreground/85">{author.bio}</p>
          <div className="mt-3 flex items-center justify-center gap-3 sm:justify-start">
            {author.linkedinUrl && (
              <a
                href={author.linkedinUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
              >
                <Linkedin className="h-3.5 w-3.5" /> LinkedIn
              </a>
            )}
            {author.contactEmail && (
              <a
                href={`mailto:${author.contactEmail}`}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
              >
                <Mail className="h-3.5 w-3.5" /> Contacter {author.name.split(' ')[0]}
              </a>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
