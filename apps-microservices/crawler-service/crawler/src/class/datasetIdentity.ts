/**
 * Règle d'identité d'une URL vis-à-vis du dataset précédent : exacte, repliée au `/` final
 * près, ou aucune. Extraite de `UpdateChecker.datasetMatch` (A312) pour que Phase 1
 * (`UrlConsolidator.addBoKnown`) et les verdicts partagent UNE règle.
 *
 * `isInDataset` est injecté : le module ne touche ni Redis ni le consolidateur.
 * Le repli vit ici, en lecture : jamais dans le SET `update_dataset:<crawlId>`.
 */
export type DatasetMatch = 'exact' | 'folded' | 'none';

export async function matchDatasetIdentity(
    url: string,
    isInDataset: (u: string) => Promise<boolean>,
): Promise<DatasetMatch> {
    if (await isInDataset(url)) {
        return 'exact';
    }
    const alt = url.endsWith('/') ? url.slice(0, -1) : url + '/';
    if (await isInDataset(alt)) {
        return 'folded';
    }
    return 'none';
}
