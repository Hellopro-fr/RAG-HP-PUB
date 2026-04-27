import replicasVsMaxSlots from './replicas_vs_max_slots';
import replicaJobMapping from './replica_job_mapping';
import peakRamExceedsAllocated from './peak_ram_exceeds_allocated';
import runningCountParity from './running_count_parity';

/** @type {import('../types').Rule[]} */
export const RULES = [
  replicasVsMaxSlots,
  replicaJobMapping,
  peakRamExceedsAllocated,
  runningCountParity,
];
