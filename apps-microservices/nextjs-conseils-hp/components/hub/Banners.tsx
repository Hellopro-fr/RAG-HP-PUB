import Image from 'next/image';
import { HubSection, CategoryTag, HubIcon } from './primitives';
import { AssistantButton, GuideButton } from './triggers';
import { BANNER_TITLE, CARD_BODY } from './typography';
import { HUB_SECTION_IDS } from '@/lib/hub/anchors';
import type { HubAccompagnementBanner, HubGuideCta, HubImage } from '@/types/hub';

/**
 * Les deux bandeaux horizontaux de la page (accompagnement, guide gratuit).
 * Même gabarit, deux contenus — d'où un composant unique paramétré.
 *
 * Le CTA ouvre le questionnaire (bannière accompagnement) ou le dialog de
 * téléchargement (bandeau guide), selon la prop `action`.
 */
interface BannerProps {
  id?: string;
  tag: string;
  tagIcon: 'phone-call' | 'book-open';
  title: string;
  text: string;
  ctaLabel: string;
  ctaIcon?: 'download';
  image?: HubImage;
  /** Quel dialog le CTA ouvre. */
  action: 'assistant' | 'guide';
  /**
   * Balise du titre.
   *
   * Les DEUX bandeaux valent `p` depuis l'arbitrage SEO du 2026-08-07 : le plan
   * de titres de la page ne retient que les intitulés porteurs de mots-clés
   * métier, et une bande CTA n'en porte pas.
   *
   * Le paramètre reste néanmoins ouvert : un bandeau qui introduirait un vrai
   * corps de contenu — ou qui deviendrait la cible d'une entrée du sommaire —
   * mériterait son `h2`. Le choix doit être fait à chaque appel, sans valeur par
   * défaut, pour qu'il ne soit jamais hérité par inadvertance.
   *
   * Explicite et sans valeur par défaut : le choix doit être fait à chaque
   * appel, pas hérité par inadvertance.
   */
  titleAs: 'h2' | 'p';
}

function Banner({ id, tag, tagIcon, title, text, ctaLabel, ctaIcon, image, action, titleAs }: BannerProps) {
  const Title = titleAs;
  return (
    <HubSection id={id}>
      <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
        {/* MOBILE : pile badge (haut-gauche) → image → titre+bouton → texte.
            DESKTOP (lg) : grille image à gauche, badge au-dessus du contenu à
            droite. Un seul markup (3 blocs réordonnés par la grille), pas de doublon. */}
        {/* `lg:gap-y-0` : la pastille et le titre sont deux lignes de la MÊME grille,
            tout écart entre eux vient d'ici. Cf. la note de l'image ci-dessous pour
            le reste de l'espace. */}
        <div className="flex flex-col gap-4 px-5 py-6 sm:px-6 lg:grid lg:grid-cols-[160px_minmax(0,1fr)] lg:items-center lg:gap-x-8 lg:gap-y-0 lg:px-8 lg:py-5">
          {/* Badge — mobile : tout en haut à gauche ; desktop : haut de la colonne droite. */}
          <div className="lg:col-start-2 lg:row-start-1">
            <CategoryTag icon={tagIcon}>{tag}</CategoryTag>
          </div>

          {image ? (
            // Boîte carrée + `object-contain` : le ratio réel est préservé sans
            // qu'on ait à déclarer les dimensions du fichier.
            //
            // ⚠️ `lg:h-24` n'est PAS un réglage esthétique. Cette boîte enjambe les
            // deux lignes de la grille (`lg:row-span-2`) : le moteur de grille
            // impose donc que ligne1 + gap + ligne2 fasse au moins sa hauteur, et
            // répartit l'excédent en mou dans les DEUX lignes. À 128 px pour 100 px
            // de contenu réel, cela injectait 10 px entre la pastille et le titre —
            // un espace qu'aucune marge ne pouvait retirer. À 96 px la boîte ne
            // contraint plus rien et les lignes retombent sur leur contenu.
            // L'agrandir de nouveau ré-ouvrira l'écart, sans que rien ne le signale.
            <div className="relative mx-auto h-32 w-full max-w-[140px] lg:col-start-1 lg:row-span-2 lg:row-start-1 lg:h-24 lg:self-center">
              <Image
                src={image.src}
                alt={image.alt}
                fill
                sizes="160px"
                className="object-contain"
              />
            </div>
          ) : (
            // Visuel non livré → pastille d'icône.
            <div className="mx-auto flex h-24 w-24 items-center justify-center rounded-2xl bg-primary/10 text-primary lg:col-start-1 lg:row-span-2 lg:row-start-1 lg:self-center">
              <HubIcon name={tagIcon} className="h-10 w-10" />
            </div>
          )}

          {/* Contenu — grille interne. MOBILE (< sm) : pile titre → texte → BOUTON
              (dernier, pleine largeur). sm+ : titre + bouton sur une ligne, texte
              dessous (disposition d'origine conservée). */}
          <div className="sm:grid sm:grid-cols-[1fr_auto] sm:items-center sm:gap-x-4 lg:col-start-2 lg:row-start-2">
            {/* `BANNER_TITLE` et non `SECTION_TITLE` : niveau intermédiaire assumé,
                le CTA partage cette ligne en sm+ (cf. typography.ts). Les classes
                de placement dans la grille restent au point d'appel — l'échelle ne
                porte que taille, graisse et interligne.
                La BALISE, elle, vient de `titleAs` : l'apparence est la même que le
                titre soit un `h2` ou un `p`. */}
            <Title className={`${BANNER_TITLE} text-foreground sm:col-start-1 sm:row-start-1`}>
              {title}
            </Title>
            <p
              className={`mt-2 ${CARD_BODY} text-muted-foreground sm:col-span-2 sm:col-start-1 sm:row-start-2`}
            >
              {text}
            </p>
            <div className="mt-4 w-full sm:col-start-2 sm:row-start-1 sm:mt-0 sm:w-auto sm:justify-self-end">
              {action === 'assistant' ? (
                // `banner_accompagnement` : ce bandeau ouvre le QUESTIONNAIRE,
                // pas le guide — d'où une valeur distincte de `banner_guide`.
                <AssistantButton
                  label={ctaLabel}
                  icon={ctaIcon}
                  entryPoint="banner_accompagnement"
                />
              ) : (
                <GuideButton
                  label={ctaLabel}
                  icon={ctaIcon}
                  variant="solid"
                  entryPoint="banner_guide"
                />
              )}
            </div>
          </div>
        </div>
      </div>
    </HubSection>
  );
}

export function AccompagnementBanner({ data }: { data: HubAccompagnementBanner }) {
  return (
    <Banner
      tag={data.tag}
      tagIcon="phone-call"
      title={data.title}
      // Hors du plan de titres (arbitré le 2026-08-07) : ce bandeau n'introduit
      // aucun contenu, il propose une action. Apparence inchangée.
      titleAs="p"
      text={data.text}
      ctaLabel={data.ctaLabel}
      image={data.image}
      action="assistant"
    />
  );
}

export function GuideCta({ data }: { data: HubGuideCta }) {
  return (
    <Banner
      id={HUB_SECTION_IDS.guideCta}
      tag={data.tag}
      tagIcon="book-open"
      title={data.title}
      // `p` depuis le 2026-08-07 : les DEUX bandeaux sortent du plan de titres.
      // Ce sont des CTA, pas des sections de contenu.
      titleAs="p"
      text={data.text}
      ctaLabel={data.ctaLabel}
      ctaIcon="download"
      image={data.image}
      action="guide"
    />
  );
}
