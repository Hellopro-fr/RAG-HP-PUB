import type { DecisionOutcome } from "./diezDecision.js";

export type DiezRoute =
    | { action: "noop" }
    | { action: "activate" }
    | { action: "commit"; decision: "skipDiez" | "bypassDiez"; source: "tier1" | "default" };

/**
 * Decide what the '#' hook should do for a tier-1 outcome. With tier-2 enabled,
 * tier-1 confidence only ACTIVATES the verification engine (the engine commits);
 * escalate defaults to bypassDiez. With tier-2 disabled, tier-1 commits directly
 * (phase-1) and escalate still defaults (zero-touch floor). See spec §3.3.
 */
export const routeDiezOutcome = (outcome: DecisionOutcome, tier2Enabled: boolean): DiezRoute => {
    if (outcome === "escalate") return { action: "commit", decision: "bypassDiez", source: "default" };
    if (tier2Enabled) {
        if (outcome === "skipDiez" || outcome === "bypassDiez" || outcome === "promoteTier2") return { action: "activate" };
        return { action: "noop" };
    }
    if (outcome === "skipDiez") return { action: "commit", decision: "skipDiez", source: "tier1" };
    if (outcome === "bypassDiez") return { action: "commit", decision: "bypassDiez", source: "tier1" };
    return { action: "noop" };
};
