/**
 * Constantes de layout partagées entre AppShell et Sidebar.
 * Utiliser `style={{ width: SIDEBAR_WIDTH }}` pour injecter dynamiquement
 * (les template literals dans className ne sont pas supportés par Tailwind JIT).
 *
 * Les classes Tailwind statiques `w-[232px]` doivent rester dans les classNames
 * pour que le JIT les inclue — voir commentaire "sync with SIDEBAR_WIDTH" en place.
 */
export const SIDEBAR_WIDTH = '232px';
