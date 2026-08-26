import Image from 'next/image';
import { HubSection, CategoryTag, HubIcon, CheckBullet } from './primitives';
import { CardCarousel } from './CardCarousel';
import { HubCardCarousel } from './HubCardCarousel';
import { AssistantButton, GuideButton } from './triggers';
import {
  CARD_BODY,
  CARD_TITLE,
  FEATURE_TITLE,
  LINK_LABEL,
  SECTION_SUBTITLE,
} from './typography';
import { sanitizeHubHtml } from '@/lib/hub/sanitize';
import type { HubInfoCard, HubOverlayCard, HubThematique } from '@/types/hub';

/**
 * Bloc thématique — LA brique réutilisable du template HUB.
 *
 * Les 4 blocs de la page (budget, dimensionnement, réglementation, équipements)
 * sont ce seul composant avec un `layout` différent. C'est ce qui permet de
 * décrire une nouvelle page HUB en n'écrivant qu'un fichier de données.
 *
 * `carousel` est rendu en grille défilante CSS (scroll-snap) : aucun JavaScript,
 * donc aucune hydratation et un contenu intégralement présent en SSR. C'est un
 * choix délibéré face à l'embla-carousel du prototype.
 */
export function ThematiqueBloc({
  data,
  alternate = false,
}: {
  data: HubThematique;
  /** Alterne le fond pour séparer visuellement deux blocs consécutifs. */
  alternate?: boolean;
}) {
  return (
    <HubSection id={data.id} className={alternate ? 'bg-surface' : ''}>
      {/* Pastille, PAS un titre — arbitré le 2026-08-07 par l'équipe SEO : le plan
          de titres ne retient que les intitulés porteurs de mots-clés, et les noms
          de clusters n'y figurent pas. Les cartes ci-dessous sont donc des `h3`
          rattachés au dernier `h2` rendu avant elles. */}
      <CategoryTag icon={data.tagIcon}>{data.tag}</CategoryTag>

      {data.intro && (
        // Même échelle que le chapeau des sections centrées : c'est le même rôle,
        // seul l'alignement diffère.
        <p className={`mt-3 max-w-3xl ${SECTION_SUBTITLE} text-muted-foreground`}>{data.intro}</p>
      )}

      <div className="mt-6">
        {/* `overlay` est requis par les layouts overlay-* (vérifié par
            registry.test.ts). On teste malgré tout sa présence plutôt que de
            poser un `!` : une donnée manquante doit dégrader, pas planter. */}
        {data.layout === 'overlay-left' && data.overlay && (
          <div className="grid gap-5 lg:grid-cols-[1.2fr_0.95fr]">
            <OverlayCard data={data.overlay} />
            <CardColumn cards={data.cards} guideLabel={data.guideButtonLabel} />
          </div>
        )}

        {data.layout === 'overlay-right' && data.overlay && (
          // Overlay en PREMIER dans le DOM → en MOBILE il passe au-dessus des cartes
          // (comme le bloc budget). Sur desktop, `lg:order-*` rétablit l'ordre
          // d'origine (cartes à gauche, overlay à droite) : rendu inchangé.
          <div className="grid gap-6 lg:grid-cols-[45fr_55fr]">
            <div className="lg:order-2">
              <OverlayCard data={data.overlay} />
            </div>
            <div className="lg:order-1">
              <CardColumn cards={data.cards} guideLabel={data.guideButtonLabel} />
            </div>
          </div>
        )}

        {data.layout === 'grid' && (
          // Mobile : carrousel standard HUB (cartes à taille pleine, sans aperçu,
          // flèches en haut + points en bas). Desktop (md+) : grille d'origine.
          // Un seul markup, `ArticleCard` inchangé, aucun doublon.
          <HubCardCarousel
            label={`Carrousel — ${data.tag}`}
            trackClass="gap-5 md:grid md:grid-cols-2 md:overflow-visible xl:grid-cols-3"
            controlsHiddenClass="md:hidden"
          >
            {data.cards.map((card) => (
              <div key={card.title} className="shrink-0 basis-full snap-start md:basis-auto">
                <ArticleCard data={card} />
              </div>
            ))}
          </HubCardCarousel>
        )}

        {data.layout === 'carousel' && (
          <CardCarousel label={`Carrousel — ${data.tag}`}>
            {data.cards.map((card) => (
              // Largeurs en fractions de la piste : 1 carte par vue sur mobile,
              // 2 sur tablette, 3 sur desktop. `gap-5` = 20px, d'où les retraits
              // (10px puis 13.34px) pour que la dernière carte tombe pile au bord.
              <li
                key={card.title}
                className="shrink-0 grow-0 basis-full snap-start sm:basis-[calc(50%-10px)] xl:basis-[calc(33.333%-13.34px)]"
              >
                <ArticleCard data={card} />
              </li>
            ))}
          </CardCarousel>
        )}
      </div>
    </HubSection>
  );
}

/**
 * Carte pleine hauteur : photo en fond, dégradé, titre et puces.
 *
 * ⚠️ `h-full` est nécessaire, pas décoratif. En `overlay-left` la carte est un
 * enfant DIRECT de la grille et le `stretch` par défaut suffit ; en
 * `overlay-right` elle est enveloppée dans un `<div class="lg:order-2">` (ajouté
 * pour l'ordre mobile). Le wrapper s'étire, l'article non : sans `h-full` il
 * retombait sur `min-h-[440px]` et la carte était visiblement plus courte que la
 * colonne de cartes en face. `min-h` reste un plancher pour les blocs peu fournis.
 */
function OverlayCard({ data }: { data: HubOverlayCard }) {
  return (
    <article className="relative h-full min-h-[440px] overflow-hidden rounded-2xl border border-border bg-neutral-900 shadow-sm">
      {data.image && (
        // `fill` : la boîte impose la hauteur, les dimensions d'origine
        // n'entrent pas en jeu. Voir le commentaire de HubImage.
        <Image
          src={data.image.src}
          alt={data.image.alt}
          fill
          sizes="(max-width: 1024px) 100vw, 55vw"
          className="object-cover"
        />
      )}
      <div className="absolute inset-0 bg-gradient-to-br from-black/95 via-black/70 to-black/30" />
      <div className="relative flex h-full flex-col justify-center p-7 sm:p-9">
        <span className="mb-4 block h-1 w-10 rounded-full bg-cta" />
        <h3 className={`max-w-md ${FEATURE_TITLE} text-white`}>{data.title}</h3>
        {/* `intro` et les puces acceptent du HTML restreint (gras sur les chiffres
            clés). Toujours assaini — cf. lib/hub/sanitize.ts. */}
        {data.intro && (
          <p
            className={`mt-4 max-w-md ${CARD_BODY} text-white/85 [&_strong]:font-semibold [&_strong]:text-white`}
            dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(data.intro) }}
          />
        )}
        <ul className="mt-6 space-y-3">
          {data.bullets.map((bullet) => (
            <li key={bullet} className={`flex items-start gap-3 ${CARD_BODY} text-white`}>
              <CheckBullet />
              <span
                className="[&_strong]:font-semibold [&_strong]:text-white"
                dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(bullet) }}
              />
            </li>
          ))}
        </ul>
        {data.ctaLabel && (
          <div className="mt-6">
            {data.href ? (
              <a
                href={data.href}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-cta px-5 text-sm font-semibold text-cta-foreground shadow-cta transition hover:bg-cta-hover"
              >
                {data.ctaLabel}
                <HubIcon name="arrow-right" className="h-4 w-4" />
              </a>
            ) : (
              <AssistantButton
                label={data.ctaLabel}
                icon="arrow-right"
                iconPosition="end"
                variant="solid"
                entryPoint="bloc_thematique"
              />
            )}
          </div>
        )}
      </div>
    </article>
  );
}

/** Colonne de cartes informatives + bouton guide optionnel. */
function CardColumn({ cards, guideLabel }: { cards: HubInfoCard[]; guideLabel?: string }) {
  return (
    <div className="flex flex-col gap-5">
      {cards.map((card) => (
        <InfoCard key={card.title} data={card} />
      ))}
      {guideLabel && (
        <GuideButton
          label={guideLabel}
          icon="download"
          className="w-full"
          entryPoint="bloc_thematique"
        />
      )}
    </div>
  );
}

/**
 * Carte informative : icône et titre SUR LA MÊME LIGNE, description, puis ligne
 * de lien séparée par un filet. C'est la structure du prototype — empiler l'icône
 * au-dessus du titre change nettement la densité de la carte.
 */
function InfoCard({ data }: { data: HubInfoCard }) {
  return (
    <article className="rounded-2xl border border-border bg-surface-muted p-5">
      <div className="flex items-start gap-4">
        {data.icon && (
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-card text-primary shadow-sm">
            <HubIcon name={data.icon} />
          </span>
        )}
        <h3 className={`${CARD_TITLE} text-foreground`}>{data.title}</h3>
      </div>

      {data.descriptionHtml ? (
        // Termes en gras en NOIR et non en bleu : ce ne sont pas des liens, et le
        // bleu leur donnait une fausse apparence de cliquable. Seules les icônes
        // restent bleues dans ce bloc.
        <div
          className={`mt-3 ${CARD_BODY} text-muted-foreground [&_strong]:font-semibold [&_strong]:text-foreground`}
          dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(data.descriptionHtml) }}
        />
      ) : (
        data.description && (
          <p className={`mt-3 ${CARD_BODY} text-muted-foreground`}>{data.description}</p>
        )
      )}

      {data.linkLabel && (
        <>
          <div aria-hidden className="mt-4 h-px w-full bg-border" />
          <div className="mt-3">
            {data.href ? (
              <a
                href={data.href}
                className={`flex w-full items-center justify-between gap-3 ${LINK_LABEL} text-foreground hover:underline`}
              >
                <span>{data.linkLabel}</span>
                <HubIcon name="arrow-right" className="h-4 w-4" />
              </a>
            ) : (
              <AssistantButton
                label={data.linkLabel}
                icon="arrow-right"
                iconPosition="end"
                variant="row"
                entryPoint="bloc_thematique"
              />
            )}
          </div>
        </>
      )}
    </article>
  );
}

/**
 * Lien « Lire l'article ».
 *
 * Avec `href` : vrai `<a>`, donc un lien interne crawlable — c'est ce qui fait la
 * valeur de maillage du HUB vers les pages conseils.
 * Sans `href` : repli sur l'ouverture du questionnaire, pour ne jamais exposer de
 * lien mort (le prototype pointait sur une ancre inexistante).
 */
function ArticleLink({ href }: { href?: string }) {
  if (!href) {
    return (
      <AssistantButton
        label="Être accompagné"
        variant="link"
        icon="arrow-right"
        iconPosition="end"
        entryPoint="bloc_thematique"
      />
    );
  }
  return (
    <a
      href={href}
      className={`inline-flex items-center gap-2 ${LINK_LABEL} text-primary hover:underline`}
    >
      Lire l’article
      <HubIcon name="arrow-right" className="h-4 w-4" />
    </a>
  );
}

/** Carte article : visuel en tête (si livré), titre, liens. */
function ArticleCard({ data }: { data: HubInfoCard }) {
  return (
    <article className="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition hover:-translate-y-1 hover:shadow-elegant">
      {data.image ? (
        <div className="relative h-52 w-full shrink-0">
          <Image
            src={data.image.src}
            alt={data.image.alt}
            fill
            sizes="(max-width: 768px) 100vw, 380px"
            className="object-cover"
          />
        </div>
      ) : (
        // Visuel non livré → bandeau neutre (cas des pages HUB sans assets).
        <div className="flex h-52 w-full shrink-0 items-center justify-center bg-surface-muted text-primary/30">
          <HubIcon name="book-open" className="h-10 w-10" />
        </div>
      )}
      <div className="flex flex-1 flex-col p-5">
        {/* `h3` et non `h4` : même niveau que les cartes des autres layouts
            (overlay, info). Toutes les cartes d'un bloc thématique sont des
            enfants directs du `h2` du cluster, quel que soit leur habillage. */}
        <h3 className={`${CARD_TITLE} text-foreground`}>{data.title}</h3>
        {/* CTA guide par carte retiré en attendant la modif serveur (formulaire guide).
            « Lire l'article » seul pour l'instant. */}
        <div className="mt-auto flex pt-5">
          <ArticleLink href={data.href} />
        </div>
      </div>
    </article>
  );
}
