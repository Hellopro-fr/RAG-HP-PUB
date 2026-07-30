import {
  Activity,
  ArrowRight,
  BookOpen,
  Calculator,
  CheckCircle2,
  CircleHelp,
  ClipboardCheck,
  ClipboardList,
  Compass,
  Download,
  Factory,
  FileText,
  HandCoins,
  Handshake,
  Headphones,
  Home,
  Lightbulb,
  Mail,
  Mailbox,
  MoreHorizontal,
  Pencil,
  Phone,
  PhoneCall,
  PiggyBank,
  Route,
  Ruler,
  Scale,
  Search,
  SearchCheck,
  ShieldCheck,
  UserRoundCheck,
  Users,
  Users2,
  Wallet,
  Wrench,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

/**
 * Registre d'icônes du template HUB.
 *
 * Pourquoi passer par un nom plutôt qu'importer l'icône dans les données :
 * un fichier `data/hub/*.ts` qui importe un composant React devient un fichier
 * React. Il ne peut plus être relu ni édité par quelqu'un qui ne connaît pas
 * la stack, et il traîne une dépendance de rendu dans une couche de contenu.
 * Même approche que `lib/categoryIcons.tsx` côté conseils.
 *
 * ⚠️ Ce registre ne contient QUE les icônes réellement utilisées. Il en a compté
 * 56 pendant un temps, dont 21 inertes : un registre qui grossit « au cas où »
 * devient impossible à auditer et laisse croire à des choix de design qui n'ont
 * jamais eu lieu. Pour en ajouter une : importer le composant lucide ci-dessus et
 * ajouter l'entrée à `HUB_ICONS`. `HubIconName` s'élargit automatiquement.
 *
 * À l'inverse, les icônes utilisées EN DUR dans un composant (`AssistantForm`,
 * `GuideDownloadDialog`, `LeadPopup`, `StickyCta`) sont importées directement de
 * `lucide-react` : elles n'ont pas à passer par ce registre, qui ne sert qu'aux
 * icônes choisies depuis les données.
 */
export const HUB_ICONS = {
  activity: Activity,
  'arrow-right': ArrowRight,
  'book-open': BookOpen,
  calculator: Calculator,
  'check-circle': CheckCircle2,
  clipboard: ClipboardList,
  'clipboard-check': ClipboardCheck,
  compass: Compass,
  download: Download,
  factory: Factory,
  'file-text': FileText,
  'hand-coins': HandCoins,
  handshake: Handshake,
  headphones: Headphones,
  help: CircleHelp,
  home: Home,
  lightbulb: Lightbulb,
  mail: Mail,
  mailbox: Mailbox,
  more: MoreHorizontal,
  pencil: Pencil,
  phone: Phone,
  'phone-call': PhoneCall,
  'piggy-bank': PiggyBank,
  route: Route,
  ruler: Ruler,
  scale: Scale,
  search: Search,
  'search-check': SearchCheck,
  shield: ShieldCheck,
  'user-check': UserRoundCheck,
  users: Users,
  'users-group': Users2,
  wallet: Wallet,
  wrench: Wrench,
} as const satisfies Record<string, LucideIcon>;

export type HubIconName = keyof typeof HUB_ICONS;

/**
 * Résout un nom d'icône, ou `null` si aucun nom n'est fourni (champ `icon`
 * optionnel côté données). Un nom invalide est impossible : `HubIconName` est
 * dérivé de HUB_ICONS, donc le typecheck l'attrape dans les fichiers de données.
 */
export function resolveHubIcon(name: HubIconName | undefined): LucideIcon | null {
  return name ? HUB_ICONS[name] : null;
}
