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
