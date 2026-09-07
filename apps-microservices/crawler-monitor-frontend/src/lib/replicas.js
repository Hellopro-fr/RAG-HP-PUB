// Liveness des replicas basee sur l'heure de reception cote navigateur.
// On prefere `receivedAt` (horloge navigateur, posee a la reception du heartbeat)
// a `timestamp` (horloge du conteneur crawler) pour etre immunise au decalage
// d'horloge entre la machine locale et le conteneur GCP. Sans ca, un skew >= TTL
// fait purger des replicas pourtant vivants (grille qui clignote toutes les 5s).
export const REPLICA_TTL_MS = 30_000;

export function replicaLastSeen(replica) {
  return replica?.receivedAt ?? replica?.timestamp ?? 0;
}

export function replicaAge(replica, now = Date.now()) {
  return now - replicaLastSeen(replica);
}

export function isReplicaLive(replica, now = Date.now()) {
  return replicaAge(replica, now) < REPLICA_TTL_MS;
}

/* -------- Série RAM agrégée (GET /api/replicas/history) -------------------- */

/** Taille de bucket de la série RAM (ms). Heartbeat ~2s → 15 points par bucket. */
export const RAM_SERIES_BUCKET_MS = 30_000;

const BYTES_PER_MB = 1024 * 1024;

/**
 * Agrège l'historique de TOUS les replicas en une courbe de RAM utilisée.
 *
 * Entrée : la charge utile de GET /api/replicas/history —
 *   { "<replicaId>": [{ ts, cpu, ram, totalRam, jobId }, …], … }
 * `ram` et `totalRam` sont en OCTETS (cf. heartbeat du crawler).
 *
 * Règle : un bucket de `bucketMs`, un point par replica (le DERNIER échantillon
 * du replica dans ce bucket — pas une moyenne : on veut l'occupation réelle à
 * l'instant le plus récent), puis somme sur les replicas. Un replica sans
 * échantillon dans le bucket ne compte pas : on ne prolonge pas un relevé mort.
 *
 * @param {Record<string, Array<{ts:number, ram:number, totalRam:number}>>} history
 * @param {number} [bucketMs]
 * @returns {{ points: number[], capacityMb: number|null, lastMb: number|null }}
 *   `points` en Mo, `capacityMb` = somme des totalRam les plus récents.
 */
export function aggregateReplicasRamSeries(history, bucketMs = RAM_SERIES_BUCKET_MS) {
  const empty = { points: [], capacityMb: null, lastMb: null };
  if (!history || typeof history !== 'object') return empty;

  const size = bucketMs > 0 ? bucketMs : RAM_SERIES_BUCKET_MS;
  /** bucketIndex -> somme des octets RAM du bucket */
  const sums = new Map();
  let capacityBytes = 0;
  let hasCapacity = false;

  for (const samples of Object.values(history)) {
    if (!Array.isArray(samples) || samples.length === 0) continue;

    /** bucketIndex -> échantillon le plus récent DE CE REPLICA */
    const latestPerBucket = new Map();
    let latest = null;

    for (const sample of samples) {
      const ts = Number(sample?.ts);
      if (!Number.isFinite(ts)) continue;
      const bucket = Math.floor(ts / size);
      const known = latestPerBucket.get(bucket);
      if (!known || ts >= Number(known.ts)) latestPerBucket.set(bucket, sample);
      if (!latest || ts >= Number(latest.ts)) latest = sample;
    }

    for (const [bucket, sample] of latestPerBucket) {
      const ram = Number(sample?.ram);
      if (!Number.isFinite(ram)) continue;
      sums.set(bucket, (sums.get(bucket) ?? 0) + ram);
    }

    // Capacité : le totalRam le plus récent de chaque replica, sommé.
    const totalRam = Number(latest?.totalRam);
    if (Number.isFinite(totalRam) && totalRam > 0) {
      capacityBytes += totalRam;
      hasCapacity = true;
    }
  }

  if (sums.size === 0) {
    return {
      points: [],
      capacityMb: hasCapacity ? capacityBytes / BYTES_PER_MB : null,
      lastMb: null,
    };
  }

  const points = [...sums.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, bytes]) => bytes / BYTES_PER_MB);

  return {
    points,
    capacityMb: hasCapacity ? capacityBytes / BYTES_PER_MB : null,
    lastMb: points[points.length - 1],
  };
}
