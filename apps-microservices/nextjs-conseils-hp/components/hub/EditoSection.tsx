import { HubSection } from './primitives';
import { sanitizeHubHtml } from '@/lib/hub/sanitize';
import { PROSE as PROSE_SCALE, SECTION_TITLE } from './typography';
import type { HubEdito } from '@/types/hub';

/**
 * Typographie du bloc : la constante `PROSE` de l'échelle partagée, plus la
 * couleur (la couleur n'est jamais dans l'échelle — cf. `typography.ts`).
 * Une seule taille, une seule couleur, le gras dans la couleur du texte courant.
 */
const PROSE = `${PROSE_SCALE} text-foreground`;

/**
 * Section éditoriale — le contenu SEO de la page.
 *
 * Server Component, colonne unique en `max-w-3xl` : c'est du texte long, la
 * largeur de lecture compte plus que l'occupation de l'écran.
 *
 * Trois formes possibles, combinables : `intro` (paragraphe), `items` (liste à
 * puces), `bodyHtml` (prose avec emphase inline, assainie). `bodyHtml` existe
 * parce que certains paragraphes ont du gras au milieu d'une phrase — impossible
 * à exprimer proprement en texte plat sans mettre du JSX dans les données.
 */
export function EditoSection({ data }: { data: HubEdito }) {
  return (
    <HubSection id={data.id} compact>
      <div className="mx-auto max-w-3xl">
        {/* `h3` et non `h2` — demandé le 2026-08-07 avec la structure de référence.
            La TAILLE reste celle d'un titre de section (`SECTION_TITLE`) : c'est le
            niveau qui change, pas l'apparence.

            ⚠️ POINT OUVERT — en attente de l'équipe SEO (2026-08-07).
            Ces blocs n'ont aucun parent thématique : le `h3` les rattache au
            dernier `h2` rendu avant eux, qui n'a aucun rapport. Avec
            `afterEditoId: 'quel-budget-prevoir'`, le plan réel donne :

              h2 Comment ça marche ?
                h3 1. Vous décrivez votre projet   … (les 4 étapes)
                h3 Quel modèle d'élevage choisir ?      ← édito
                h3 Pourquoi se faire accompagner ?      ← édito

            Les deux éditos se lisent comme les étapes 5 et 6 du processus, alors
            que c'est le contenu le plus riche en mots-clés de la page. Idem pour
            les deux premiers, rattachés à « Explorez les grandes étapes » qui
            n'est qu'une rangée de tuiles de navigation.

            Deux sorties possibles :
             a) `h2` — ce sont des sections de plein droit (retour à l'état d'avant) ;
             b) un `h2` chapeau avant le premier édito (ex. « Tout savoir sur votre
                projet… »), les éditos restant en `h3` dessous. Meilleur SEO, mais
                demande un titre par page et un champ de plus dans `HubPage`.
            Ne pas laisser en l'état sans décision. */}
        <h3 className={`${SECTION_TITLE} text-foreground`}>{data.title}</h3>

        {/* `intro`, `items` et `note` acceptent du HTML restreint, comme `bodyHtml` :
            les chiffres clés et les intitulés de puce sont mis en gras au milieu
            des phrases. Tout passe par le même sanitizer. */}
        {data.intro && (
          <p
            className={`mt-4 ${PROSE}`}
            dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(data.intro) }}
          />
        )}

        {data.bodyHtml && (
          <div
            className={`mt-4 space-y-4 ${PROSE} [&_li]:ml-5 [&_li]:list-disc [&_ul]:space-y-3`}
            dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(data.bodyHtml) }}
          />
        )}

        {data.items && data.items.length > 0 && (
          <ul className="mt-4 space-y-2">
            {data.items.map((item) => (
              <li key={item} className={`flex items-start gap-2.5 ${PROSE}`}>
                {/* Pastille en noir : elle était bleue, seule touche de couleur
                    d'un bloc autrement monochrome. */}
                <span
                  aria-hidden
                  className="mt-[0.55rem] h-1.5 w-1.5 shrink-0 rounded-full bg-foreground"
                />
                <span dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(item) }} />
              </li>
            ))}
          </ul>
        )}

        {data.note && (
          // Même typographie que le reste ; c'est le cadre qui distingue l'encart,
          // pas une taille ni une couleur de texte différentes.
          <p
            className={`mt-6 rounded-2xl border border-border bg-surface p-5 ${PROSE}`}
            dangerouslySetInnerHTML={{ __html: sanitizeHubHtml(data.note) }}
          />
        )}
      </div>
    </HubSection>
  );
}
