/**
 * A545 — hôtes exclus du crawl.
 *
 * Au lancement du job, le BO envoie la liste des hôtes à NE PAS crawler : un sous-domaine qui est
 * un AUTRE domaine de la base (ex. `collectivites.dpc.fr` sous `dpc.fr`). Le contrôle s'AJOUTE aux
 * contrôles `includes` de routes.ts (mise en file et handler), sans les remplacer.
 *
 * Comparaison par SUFFIXE, jamais `includes` : `xcollectivites.dpc.fr` n'est pas un sous-domaine
 * de `collectivites.dpc.fr`, et le parent `dpc.fr` n'est pas exclu par `collectivites.dpc.fr`.
 */

/**
 * Ramène une entrée du BO à un hôte nu : minuscules ; schéma, chemin, point final et `www.`
 * retirés (choix 3a de la fiche : une entrée mal formée est nettoyée, ni refusée ni ignorée).
 */
export function normalizeExcludedHost(raw: string): string {
    let host = (raw || "").trim().toLowerCase();
    host = host.replace(/^[a-z][a-z0-9+.-]*:\/\//, ""); // schéma
    host = host.split(/[/?#]/)[0];                       // chemin, requête, ancre
    host = host.replace(/\.+$/, "");                     // point final
    host = host.replace(/^www\./, "");
    return host;
}

/** Valeur de `--excludehosts` (entrées séparées par « ; ») ⇒ hôtes normalisés, sans vide ni doublon. */
export function parseExcludedHosts(raw: string | undefined): string[] {
    const hosts: string[] = [];
    for (const part of (raw || "").split(";")) {
        const host = normalizeExcludedHost(part);
        if (host && !hosts.includes(host)) hosts.push(host);
    }
    return hosts;
}

/** Vrai si `host` est l'un des hôtes exclus ou l'un de leurs sous-domaines. Liste vide ⇒ jamais exclu. */
export function isExcludedHost(host: string, excluded: readonly string[]): boolean {
    if (!host || excluded.length === 0) return false;
    const h = host.toLowerCase().replace(/\.+$/, "");
    return excluded.some((e) => h === e || h.endsWith("." + e));
}
