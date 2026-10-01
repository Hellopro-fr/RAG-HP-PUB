import type { HubAccompagnement, HubFaq, HubHowItWorks } from '@/types/hub';

/**
 * Contenus PARTAGÉS par toutes les pages HUB.
 *
 * Ce fichier n'existe que pour les blocs dont le texte est identique d'une
 * verticale à l'autre. Y placer un contenu spécifique à un métier ferait perdre
 * tout l'intérêt : les 3 pages HUB (élevage, food truck, laverie) n'ont rien en
 * commun côté sujet, seulement côté parcours HelloPro.
 *
 * Le préfixe `_` le distingue des fichiers de page dans le dossier.
 */

/**
 * Parcours « Comment ça marche ? » — validé comme RÉFÉRENCE pour tous les
 * templates (29/07/2026).
 *
 * Volontairement sans vocabulaire métier : « votre besoin » et « votre démarche »
 * au lieu de « votre projet d'élevage », « conseiller » au lieu d'« expert
 * avicole ». C'est ce qui permet de le réutiliser tel quel sur les 3 pages, et
 * d'éviter trois copies qui divergeraient à la première retouche.
 *
 * `afterEditoId` reste à la charge de chaque page : les identifiants d'edito
 * diffèrent d'une verticale à l'autre.
 */
export const HOW_IT_WORKS: Omit<HubHowItWorks, 'afterEditoId'> = {
  title: 'Comment ça marche ?',
  steps: [
    {
      icon: 'pencil',
      title: 'Vous décrivez votre besoin',
      desc: 'Remplissez le formulaire en quelques minutes pour nous parler de votre besoin.',
    },
    {
      icon: 'search-check',
      title: 'Nous qualifions votre besoin',
      desc: 'Nos conseillers analysent vos réponses et préparent des recommandations personnalisées.',
    },
    {
      icon: 'phone-call',
      title: 'Un conseiller vous contacte',
      desc: 'Un conseiller vous appelle pour comprendre vos enjeux et affiner les solutions.',
    },
    {
      icon: 'users-group',
      title: 'Nous vous mettons en relation',
      desc: 'Vous êtes mis en relation avec des fournisseurs sélectionnés, au bon moment de votre démarche.',
    },
  ],
};

/**
 * Bloc « Un accompagnement humain » — validé comme RÉFÉRENCE pour tous les
 * templates (29/07/2026). Générique lui aussi : « votre besoin » et
 * « conseiller », aucun vocabulaire métier.
 *
 * L'`image` reste à la charge de chaque page : le visuel vit sous
 * `/images/hub/<slug>/`, et chaque verticale peut vouloir sa propre photo.
 */
export const ACCOMPAGNEMENT: Omit<HubAccompagnement, 'image'> = {
  title: 'Un accompagnement humain, simple et efficace',
  text:
    '<p>Nous prenons le temps de comprendre votre besoin pour vous mettre en relation avec les bons fournisseurs, au bon moment.</p>' +
    '<p>Notre objectif : des solutions pertinentes et un projet qui avance.</p>',
  points: [
    'Accompagnement par un conseiller',
    'Solutions adaptées à votre besoin',
    'Mise en relation progressive et ciblée',
    'Service 100 % gratuit et sans engagement',
  ],
};

/**
 * FAQ — validée comme RÉFÉRENCE pour tous les templates (29/07/2026).
 *
 * Elle porte sur le PARCOURS HelloPro (qualification, mise en relation, gratuité),
 * jamais sur le métier : d'où sa réutilisation intégrale sur les 3 verticales.
 *
 * `title` reste « FAQ » : `FaqBlock` détecte ce libellé générique et affiche
 * « FAQ : Vos questions les plus fréquentes ».
 *
 * ⚠️ Conséquence à connaître : les 3 pages HUB exposeront le même contenu de FAQ
 * et donc le même balisage `FAQPage`. Acceptable — Google a restreint les rich
 * results FAQ aux sites institutionnels depuis 2023, ce balisage n'apporte plus de
 * rendu enrichi — mais si une verticale mérite ses propres questions un jour,
 * c'est ici qu'il faudra cesser de mutualiser.
 */
export const FAQ: HubFaq = {
  title: 'FAQ',
  items: [
    {
      q: 'Comment Hellopro m’accompagne-t-il dans ma démarche ?',
      a: 'Hellopro analyse votre besoin, vous accompagne dans sa qualification, puis vous met progressivement en relation avec les fournisseurs les plus adaptés.',
    },
    {
      q: 'Suis-je accompagné par un conseiller ?',
      a: 'Oui. Un conseiller Hellopro peut vous contacter afin de mieux comprendre votre besoin, préciser vos contraintes et vous orienter dans les prochaines étapes.',
    },
    {
      q: 'Comment les fournisseurs sont-ils sélectionnés ?',
      a: 'Les fournisseurs sont sélectionnés selon votre besoin, vos critères, vos contraintes et les informations recueillies au cours de la qualification.',
    },
    {
      q: 'Dois-je contacter directement les fournisseurs ?',
      a: 'Pas nécessairement. Hellopro qualifie d’abord votre demande afin de vous orienter vers les interlocuteurs les plus pertinents au bon moment.',
    },
    {
      q: 'Que se passe-t-il après avoir rempli le formulaire ?',
      a: 'Votre demande est analysée par Hellopro. Un conseiller peut ensuite vous contacter pour la préciser avant de vous mettre en relation avec des fournisseurs adaptés.',
    },
    {
      q: 'Le service Hellopro est-il gratuit ?',
      a: 'Oui. Le service d’accompagnement et de mise en relation proposé par Hellopro est entièrement gratuit et sans engagement.',
    },
    {
      q: 'Puis-je avancer sans être rappelé par un conseiller ?',
      a: 'Oui. Toutefois, un échange avec un conseiller permet de mieux préciser votre besoin et de bénéficier de mises en relation plus pertinentes.',
    },
    {
      q: 'Pourquoi passer par Hellopro plutôt que contacter directement un fournisseur ?',
      a: 'Hellopro vous aide à structurer votre besoin, à identifier les solutions pertinentes et à accéder plus rapidement aux fournisseurs adaptés à votre situation.',
    },
  ],
};
