import replicasVsMaxSlots from './replicas_vs_max_slots';
import replicaJobMapping from './replica_job_mapping';
import peakRamExceedsAllocated from './peak_ram_exceeds_allocated';

/** @type {import('../types').Rule[]} */
export const RULES = [replicasVsMaxSlots, replicaJobMapping, peakRamExceedsAllocated];
