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
   * RÈGLE (arbitrée le 2026-08-07) : **un titre introduit un corps de contenu.**
   * Contrainte supplémentaire : toute entrée du sommaire doit atterrir sur un titre.
   *
   * - `h2` si le bandeau porte un `id` référencé dans `page.nav` : le titre
   *   annonce l'arrivée à qui a cliqué dans le sommaire (cas de `GuideCta`).
   * - `p` sinon : une bande CTA sans ancre n'est la destination de rien et
   *   n'introduit aucun contenu. L'inscrire au plan de titres y ajoute une entrée
   *   qui ne mène nulle part — un lecteur d'écran qui navigue par titres y
   *   atterrit pour n'y trouver qu'une phrase et un bouton
   *   (cas de `AccompagnementBanner`).
   *
   * ⚠️ Ne pas en déduire « rien d'autre qu'une entrée du sommaire n'est un
   * titre » : `AccompagnementSplit` est absent du sommaire et garde son `h2`,
   * parce qu'il a un vrai corps de texte. C'est le contenu qui décide.
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
        <div className="flex flex-col gap-4 px-5 py-6 sm:px-6 lg:grid lg:grid-cols-[160px_minmax(0,1fr)] lg:items-center lg:gap-x-8 lg:gap-y-2 lg:px-8 lg:py-5">
          {/* Badge — mobile : tout en haut à gauche ; desktop : haut de la colonne droite. */}
          <div className="lg:col-start-2 lg:row-start-1">
            <CategoryTag icon={tagIcon}>{tag}</CategoryTag>
          </div>

          {image ? (
            // Boîte carrée + `object-contain` : le ratio réel est préservé sans
            // qu'on ait à déclarer les dimensions du fichier.
            <div className="relative mx-auto h-32 w-full max-w-[140px] lg:col-start-1 lg:row-span-2 lg:row-start-1 lg:self-center">
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
                <AssistantButton label={ctaLabel} icon={ctaIcon} />
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
      // `h2` CONSERVÉ, contrairement au bandeau accompagnement — la différence
      // n'est pas cosmétique : ce bandeau porte `id="guide-gratuit"` et c'est une
      // ENTRÉE DU SOMMAIRE. Qui clique « Guide gratuit » atterrit ici, et un titre
      // lui annonce où il est. Le bandeau accompagnement n'a pas d'id et n'est la
      // destination de rien : son titre n'introduisait aucune arrivée.
      titleAs="h2"
      text={data.text}
      ctaLabel={data.ctaLabel}
      ctaIcon="download"
      image={data.image}
      action="guide"
    />
  );
}
