"use client";

import ProfileTypeStep from '@/components/flow/ProfileTypeStep';
import MatchingLoader from '@/components/flow/MatchingLoader';
import { useFlowNavigation } from '@/hooks/useFlowNavigation';
import { useProcessMatchingLogic } from '@/hooks/api/useProcessMatchingLogic';

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
  const { goToSelection, goToQuestionnaire } = useFlowNavigation();
  const { showLoader, submitProfile, resetLoader } = useProcessMatchingLogic();

  const handleLoaderComplete = () => {
    // Reset loader state before navigation
    resetLoader();
    // Navigate to selection step after loader finishes (with GET params preserved)
    goToSelection();
  };

  const handleBack = () => {
    // Navigate back to questionnaire (with GET params preserved)
    goToQuestionnaire();
  };

  if (showLoader) {
    return <MatchingLoader onComplete={handleLoaderComplete} duration={5000} />;
  }

  return (
    <ProfileTypeStep
      onComplete={submitProfile}
      onBack={handleBack}
      priorityCountries={priorityCountries}
      otherCountries={otherCountries}
    />
  );
}
