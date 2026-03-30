"use client";

import ProfileTypeStep from '@/components/flow/ProfileTypeStep';
// import MatchingLoader from '@/components/flow/MatchingLoader';
import { useFlowNavigation } from '@/hooks/useFlowNavigation';
// import { useProcessMatchingLogic } from '@/hooks/api/useProcessMatchingLogic';
import { useFlowStore } from '@/lib/stores/flow-store';
import { consolidateEquivalences } from '@/lib/utils/equivalence-merger';
import { useDbTracking } from '@/hooks/tracking/useDbTracking';
import type { ProfileData } from '@/types';

interface Country {
  id: number;
  libelle: string;
}

interface ProfileClientProps {
  priorityCountries: Country[];
  otherCountries: Country[];
}

export default function ProfileClient({
  priorityCountries,
  otherCountries,
}: ProfileClientProps) {
  const { goToSelection } = useFlowNavigation();
  // const { goToSomethingToAdd } = useFlowNavigation();
  // const { showLoader, submitProfile, redirectGoToSomethingToAdd } = useProcessMatchingLogic();
  const { geoData, categoryId, dynamicEquivalences, setEquivalenceCaracteristique } = useFlowStore();
  const { trackDbEvent } = useDbTracking();

  // submitProfile inliné depuis useProcessMatchingLogic (logique active uniquement)
  const submitProfile = async (data: ProfileData) => {
    const consolidated = consolidateEquivalences(dynamicEquivalences);
    setEquivalenceCaracteristique(consolidated);
    trackDbEvent('profile', 'complete', {
      profile_type: data?.type,
      country: data?.country,
      equivalences_count: consolidated.length
    }, categoryId, 1);
  };

  // // [DEPRECATED] Code mort — showLoader n'était jamais true, redirectGoToSomethingToAdd toujours false
  // const handleLoaderComplete = () => {
  //   // Navigate directly - no need to reset loader state
  //   // The component will unmount and state will be cleaned up automatically
  //   if (redirectGoToSomethingToAdd) {
  //     goToSomethingToAdd();
  //   } else {
  //     goToSelection();
  //   }
  // };

  const handleBack = () => {
    // Navigate back to selection/contact step
    goToSelection();
  };

  // // [DEPRECATED] showLoader n'était jamais activé (setShowLoader(true) était commenté dans useProcessMatchingLogic)
  // if (showLoader) {
  //   return <MatchingLoader onComplete={handleLoaderComplete} duration={5000} />;
  // }

  return (
    <ProfileTypeStep
      onComplete={submitProfile}
      onBack={handleBack}
      priorityCountries={priorityCountries}
      otherCountries={otherCountries}
      geoData={geoData || undefined}
    />
  );
}
