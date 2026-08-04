import { HubSection, HubIcon } from './primitives';
import { HUB_SECTION_IDS } from '@/lib/hub/anchors';
import type { HubValueProps } from '@/types/hub';

/**
 * Bandeau « Ce que vous gagnez » — au survol, la carte s'assombrit et révèle sa
 * description (motif du centre de ressources Asana).
 *
 * ⚠️ LA CARTE NE CHANGE NI DE LARGEUR NI DE HAUTEUR.
 * Une première version faisait grossir la carte active (`flex-grow: 1.6`) :
 * toute la rangée se réorganisait au moindre passage de souris, effet « tout
 * bouge ». Mesures prises sur la page Asana : cartes strictement identiques,
 * 331 px de large et 427 px de haut, survolée comme au repos.
 *
 * LE MÉCANISME RÉEL : la hauteur est FIXE, le bloc de texte est ancré en BAS, et
 * la zone d'icône absorbe l'espace (`flex-1`). Quand la description se déplie, le
 * bloc de texte grandit, la zone d'icône se comprime d'autant — l'icône et le
 * titre remontent, la description apparaît, et l'encombrement total ne bouge pas.
 * `overflow-hidden` clippe si le texte dépasse. C'est ce qui donne l'impression
 * que « seul le contenu change » : aucune boîte ne se redimensionne.
 * Ne réintroduire ni transition de largeur/hauteur, ni `scale`, ni `translate`.
 *
 * L'ICÔNE SE RÉDUIT AU SURVOL (96px → 64px), comme l'illustration Asana. Double
 * effet : au repos elle occupe le vide entre le haut de la carte et le titre — le
 * gros espace mort qui avait été signalé — et au survol elle libère la place que
 * prend la description. Sa boîte est centrée verticalement dans la zone tampon,
 * pas alignée en haut, sinon le vide se déplacerait simplement sous l'icône.
 *
 * ⚠️ AUCUNE ROTATION AUTOMATIQUE.
 * Asana n'en a pas, et une carte qui se déplie toute seule toutes les 3,5 s
 * détourne l'attention pendant la lecture du reste de la page. C'est ce qui
 * permet à ce composant d'être un SERVER COMPONENT : sans état ni minuteur, le
 * survol est géré en CSS pur (`group-hover`). Zéro JavaScript, zéro hydratation,
 * et l'effet fonctionne avant même que le bundle soit chargé.
 *
 * ⚠️ INVARIANT SEO — le texte reste TOUJOURS dans le DOM.
 * La description est repliée par `max-height` + `opacity`, jamais démontée. C'est
 * aussi ce que fait Asana, dont chaque carte contient son texte dans le HTML
 * servi (vérifié). Ne jamais remplacer ce repli CSS par un rendu conditionnel.
 *
 * Accessibilité — deux échappatoires, toutes deux en CSS :
 *  - sous `lg` : tout est déplié (pas de survol sur écran tactile) ;
 *  - `motion-reduce` : tout est déplié (ces cartes n'ont pas de lien à focaliser,
 *    faute de CTA dans les données — c'est le seul moyen d'atteindre le texte
 *    sans souris).
 */
export function ValueProps({ data }: { data: HubValueProps }) {
  return (
    <HubSection id={HUB_SECTION_IDS.valueProps} className="bg-surface" compact>
      <div className="mx-auto max-w-3xl text-center">
        <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          {data.title}
        </h2>
        <p className="mt-2 text-base text-muted-foreground sm:text-lg">{data.subtitle}</p>
      </div>

      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {data.items.map((item) => {
          const isPrimary = item.accent === 'primary';

          return (
            <article
              key={item.title}
              // Hauteur fixe + overflow-hidden : c'est ce qui empêche tout
              // redimensionnement. `transition-colors` uniquement sur la carte.
              className="group flex h-full min-h-[19rem] flex-col overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-sm transition-colors duration-300 lg:hover:border-transparent lg:hover:bg-navy-deep lg:hover:shadow-elegant"
            >
              <span className="inline-flex w-fit items-center rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider text-primary transition-colors duration-300 lg:group-hover:bg-white/15 lg:group-hover:text-white">
                {item.tag}
              </span>

              {/* Zone tampon : absorbe l'espace au repos, se comprime quand la
                  description se déplie. C'est elle qui fait remonter l'icône.
                  `items-center` : au repos l'icône se cale au MILIEU de l'espace
                  libre. Alignée en haut, elle laissait un vide sous elle — c'est
                  la critique qui a motivé ce réglage. */}
              <div className="flex flex-1 items-center py-3">
                <span
                  // La BOÎTE est animée, pas un `scale` : avec un `scale` la boîte
                  // continuerait à réserver 96px, la zone tampon ne se libérerait
                  // pas et l'icône serait clippée au dépliage. La hauteur de carte
                  // étant fixe, animer la boîte ne décale rien sur la page.
                  className={`flex h-24 w-24 shrink-0 items-center justify-center rounded-full border-2 transition-all duration-500 ease-out lg:group-hover:h-16 lg:group-hover:w-16 lg:motion-reduce:h-16 lg:motion-reduce:w-16 ${
                    isPrimary
                      ? 'border-primary/40 text-primary lg:group-hover:border-white/30 lg:group-hover:bg-primary lg:group-hover:text-primary-foreground'
                      : 'border-cta/40 text-cta lg:group-hover:border-white/30 lg:group-hover:bg-cta lg:group-hover:text-cta-foreground'
                  }`}
                >
                  <HubIcon
                    name={item.icon}
                    className="h-11 w-11 transition-all duration-500 ease-out lg:group-hover:h-8 lg:group-hover:w-8 lg:motion-reduce:h-8 lg:motion-reduce:w-8"
                  />
                </span>
              </div>

              {/* Bloc de texte ancré en bas : il grandit vers le HAUT. */}
              <div className="shrink-0">
                <h3 className="text-lg font-bold leading-tight text-foreground transition-colors duration-300 lg:group-hover:text-white">
                  {item.title}
                </h3>
                <span className="mt-2 block h-1 w-10 rounded-full bg-cta" />

                {/*
                  Repli CSS uniquement — le texte reste dans le DOM.
                  Déplié en permanence sous `lg` et sous `motion-reduce`.
                  `translate-y-3 → 0` : le texte MONTE en apparaissant, au lieu de
                  se déplier sur place. C'est ce glissement par le bas qui donne
                  l'effet Asana ; sans lui, la révélation paraît mécanique.
                */}
                <div className="mt-3 max-h-40 translate-y-0 overflow-hidden opacity-100 transition-all duration-500 ease-out lg:mt-0 lg:max-h-0 lg:translate-y-3 lg:opacity-0 lg:group-hover:mt-3 lg:group-hover:max-h-40 lg:group-hover:translate-y-0 lg:group-hover:opacity-100 lg:motion-reduce:mt-3 lg:motion-reduce:max-h-40 lg:motion-reduce:translate-y-0 lg:motion-reduce:opacity-100">
                  <p className="text-sm leading-relaxed text-muted-foreground transition-colors duration-300 lg:group-hover:text-white/80">
                    {item.desc}
                  </p>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <p className="mt-8 text-center text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
        {data.closing}
      </p>
    </HubSection>
  );
}
