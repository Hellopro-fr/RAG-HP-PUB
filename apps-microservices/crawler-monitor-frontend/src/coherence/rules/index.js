import replicasVsMaxSlots from './replicas_vs_max_slots';
import replicaJobMapping from './replica_job_mapping';

/** @type {import('../types').Rule[]} */
export const RULES = [replicasVsMaxSlots, replicaJobMapping];
