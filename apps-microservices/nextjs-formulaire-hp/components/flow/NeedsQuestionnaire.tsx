'use client';

import { useEffect, useRef } from "react";
import ProgressHeader from "./ProgressHeader";
import QuestionScreen from "./QuestionScreen";
import { useFlowStore } from "@/lib/stores/flow-store";
import { useDynamicQuestionnaire } from "@/hooks/api/useDynamicQuestionnaire";
import {
  trackGTMFunnelStart,
  trackQuestionView,
  trackGTMQuestionnaireComplete,
  setFunnelContext,
} from "@/lib/analytics";

interface NeedsQuestionnaireProps {
  onComplete: (answers: Record<number, string[]> | Record<string, string[]>) => void;
  // rubriqueId est nécessaire pour charger les questions depuis l'API
  rubriqueId?: string;
}

const STEPS = [
  { id: 1, label: "Votre besoin" },
  { id: 2, label: "Sélection" },
  { id: 3, label: "Demande de devis" },
];

const NeedsQuestionnaire = ({ onComplete, rubriqueId }: NeedsQuestionnaireProps) => {
  // Store Zustand pour persistance dans sessionStorage
  const {
    dynamicAnswers,
    setDynamicAnswer,
    setStartTime,
    startTime,
  } = useFlowStore();

  // Hook pour le questionnaire dynamique
  const dynamicQuestionnaire = useDynamicQuestionnaire(rubriqueId || '');

  // Si pas de rubriqueId, afficher une erreur
  if (!rubriqueId) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col bg-background">
        <ProgressHeader steps={STEPS} currentStep={1} progress={0} />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-4">
            <p className="text-destructive">Identifiant de catégorie manquant</p>
            <p className="text-sm text-muted-foreground">
              Veuillez sélectionner une catégorie pour continuer
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Ref pour éviter les doubles appels en StrictMode
  const hasTrackedStart = useRef(false);
  const lastTrackedQuestionIndex = useRef(-1);

  // Initialiser le timestamp de début du funnel et tracker le début
  useEffect(() => {
    if (!startTime) {
      setStartTime(Date.now());
    }

    // Track funnel start (une seule fois)
    if (!hasTrackedStart.current) {
      hasTrackedStart.current = true;
      // Initialiser le contexte avec rubrique_id
      if (rubriqueId) {
        setFunnelContext({
          rubrique_id: parseInt(rubriqueId, 10),
        });
      }
      trackGTMFunnelStart();
    }
  }, [startTime, setStartTime, rubriqueId]);

  // Quand le questionnaire dynamique est terminé
  useEffect(() => {
    if (dynamicQuestionnaire.isComplete) {
      const timeSpent = startTime ? Math.round((Date.now() - startTime) / 1000) : 0;
      trackGTMQuestionnaireComplete(dynamicQuestionnaire.progress.total, timeSpent);
      onComplete(dynamicAnswers);
    }
  }, [dynamicQuestionnaire.isComplete, dynamicQuestionnaire.progress.total, dynamicAnswers, onComplete, startTime]);

  // Hook de tracking de vue de question
  useEffect(() => {
    if (dynamicQuestionnaire.currentQuestion && lastTrackedQuestionIndex.current !== dynamicQuestionnaire.currentIndex) {
      lastTrackedQuestionIndex.current = dynamicQuestionnaire.currentIndex;
      trackQuestionView(dynamicQuestionnaire.currentIndex, {
        question_id: dynamicQuestionnaire.currentQuestion.id,
        question_title: dynamicQuestionnaire.currentQuestion.title,
        total_questions: dynamicQuestionnaire.progress.total,
      });
    }
  }, [dynamicQuestionnaire.currentIndex, dynamicQuestionnaire.currentQuestion, dynamicQuestionnaire.progress.total]);

  const {
    currentQuestion,
    currentIndex,
    isLoading,
    error,
    progress,
    submitAnswer,
    goBack,
    canGoBack,
  } = dynamicQuestionnaire;

  const LoadingScreen = ({ progress = 0 }: { progress?: number }) => (
      <div className="fixed inset-0 z-50 flex flex-col bg-background">
        <ProgressHeader steps={STEPS} currentStep={1} progress={progress} />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-4">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
            <p className="text-muted-foreground">Chargement des questions...</p>
          </div>
        </div>
      </div>
    );

    // Loading state
    if (isLoading) {
      return <LoadingScreen/>;
    }

    // Error state
    if (error) {
      return (
        <div className="fixed inset-0 z-50 flex flex-col bg-background">
          <ProgressHeader steps={STEPS} currentStep={1} progress={0} />
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center space-y-4">
              <p className="text-destructive">Erreur lors du chargement des questions</p>
              <button
                onClick={() => window.location.reload()}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg"
              >
                Réessayer
              </button>
            </div>
          </div>
        </div>
      );
    }

    // No question available
    if (!currentQuestion) {
      if (dynamicQuestionnaire.isComplete || dynamicQuestionnaire.isLoading) {
        return <LoadingScreen/>;
      }

      return (
        <div className="fixed inset-0 z-50 flex flex-col bg-background">
          <ProgressHeader steps={STEPS} currentStep={1} progress={0} />
          <div className="flex-1 flex items-center justify-center">
            <p className="text-muted-foreground">Aucune question disponible</p>
          </div>
        </div>
      );
    }

    // Calculate progress for step 1 (0-33%)
    const questionProgress = progress.percent * 0.33;

    const handleDynamicSelectAnswer = (answerCode: string) => {
      const questionCode = currentQuestion.code || `Q${currentIndex + 1}`;
      const currentAnswers = dynamicAnswers[questionCode] || [];

      if (currentQuestion.type === 'multi') {
        // Toggle la sélection
        const nextAnswers = currentAnswers.includes(answerCode)
          ? currentAnswers.filter((code) => code !== answerCode)
          : [...currentAnswers, answerCode];

        // Extraire les équivalences pour TOUTES les réponses actuellement sélectionnées
        const selectedEquivalences = currentQuestion.answers
          .filter((a: { code: string }) => nextAnswers.includes(a.code))
          .flatMap((a: { equivalence?: any[] }) => a.equivalence || []);

        setDynamicAnswer(questionCode, nextAnswers, selectedEquivalences);
      } else {
        // Mode Single : On utilise la fonction submitAnswer du hook
        submitAnswer([answerCode]);
      }
    };

    const handleDynamicNext = () => {
      const questionCode = currentQuestion.code || `Q${currentIndex + 1}`;
      const currentAnswers = dynamicAnswers[questionCode] || [];
      
      if (currentAnswers.length > 0) {
        // Utilisez la méthode du hook ! Elle gère l'extraction des équivalences 
        // ET le passage à la question suivante (setCurrentIndex)
        submitAnswer(currentAnswers);
      }
    };

    // Adapter la question dynamique au format QuestionScreen
    const adaptedQuestion = {
      id: currentQuestion.id || currentIndex + 1,
      title: currentQuestion.title,
      justification: currentQuestion.justification || '',
      multiSelect: currentQuestion.type === 'multi',
      answers: currentQuestion.answers?.map((a: { code: string; mainText: string; secondaryText?: string }) => ({
        id: a.code,
        mainText: a.mainText,
        secondaryText: a.secondaryText,
      })) || [],
    };

    const questionCode = currentQuestion.code || `Q${currentIndex + 1}`;

    return (
      <div className="fixed inset-0 z-50 flex flex-col bg-background">
        <ProgressHeader
          steps={STEPS}
          currentStep={1}
          progress={questionProgress}
        />

        <div className="flex-1 overflow-y-auto">
          <QuestionScreen
            question={adaptedQuestion}
            currentIndex={currentIndex}
            totalQuestions={progress.total}
            selectedAnswers={dynamicAnswers[questionCode] || []}
            otherText=""
            onSelectAnswer={handleDynamicSelectAnswer}
            onOtherTextChange={() => {}}
            onNext={handleDynamicNext}
            onBack={goBack}
            isFirst={!canGoBack}
            isLast={currentIndex === progress.total - 1}
          />
        </div>
      </div>
    );
};

export default NeedsQuestionnaire;
