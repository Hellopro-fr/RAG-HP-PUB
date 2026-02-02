'use client';

import { useState, useEffect, useRef } from "react";
import ProgressHeader from "./ProgressHeader";
import QuestionScreen from "./QuestionScreen";
import { QUESTIONS } from "@/data/questions";
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
  // Si rubriqueId est fourni, on utilise le mode dynamique (API)
  // Sinon, on utilise les questions statiques
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
    userAnswers,
    otherTexts,
    dynamicAnswers,
    setAnswer,
    setOtherText,
    setDynamicAnswer,
    setStartTime,
    startTime,
  } = useFlowStore();

  // Mode dynamique si rubriqueId est fourni
  const isDynamicMode = !!rubriqueId;

  // Hook pour le mode dynamique
  const dynamicQuestionnaire = useDynamicQuestionnaire(rubriqueId || '');

  // State pour le mode statique
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);

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
    if (isDynamicMode && dynamicQuestionnaire.isComplete) {
      const timeSpent = startTime ? Math.round((Date.now() - startTime) / 1000) : 0;
      trackGTMQuestionnaireComplete(dynamicQuestionnaire.progress.total, timeSpent);
      onComplete(dynamicAnswers);
    }
  }, [isDynamicMode, dynamicQuestionnaire.isComplete, dynamicQuestionnaire.progress.total, dynamicAnswers, onComplete, startTime]);

  // Hook de tracking de vue (Dynamique ET Statique combinés ou séparés mais TOUJOURS présents)
  useEffect(() => {
    if (isDynamicMode) {
      if (dynamicQuestionnaire.currentQuestion && lastTrackedQuestionIndex.current !== dynamicQuestionnaire.currentIndex) {
        lastTrackedQuestionIndex.current = dynamicQuestionnaire.currentIndex;
        trackQuestionView(dynamicQuestionnaire.currentIndex, {
          question_id: dynamicQuestionnaire.currentQuestion.id,
          question_title: dynamicQuestionnaire.currentQuestion.title,
          total_questions: dynamicQuestionnaire.progress.total,
        });
      }
    } else {
      const currentStatQuestion = QUESTIONS[currentQuestionIndex];
      if (lastTrackedQuestionIndex.current !== currentQuestionIndex) {
        lastTrackedQuestionIndex.current = currentQuestionIndex;
        trackQuestionView(currentQuestionIndex, {
          question_id: currentStatQuestion.id,
          question_title: currentStatQuestion.title,
          total_questions: QUESTIONS.length,
        });
      }
    }
  }, [isDynamicMode, dynamicQuestionnaire.currentIndex, currentQuestionIndex, dynamicQuestionnaire.currentQuestion]);

  // === MODE DYNAMIQUE ===
  if (isDynamicMode) {  
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

    // Track question view en mode dynamique
    // useEffect(() => {
    //   if (currentQuestion && lastTrackedQuestionIndex.current !== currentIndex) {
    //     lastTrackedQuestionIndex.current = currentIndex;
    //     trackQuestionView(currentIndex, {
    //       question_id: currentQuestion.id || currentIndex + 1,
    //       question_title: currentQuestion.title,
    //       total_questions: progress.total,
    //     });
    //   }
    // }, [currentQuestion, currentIndex, progress.total]);

    // Calculate progress for step 1 (0-33%)
    const questionProgress = progress.percent * 0.33;

    const handleDynamicSelectAnswer = (answerCode: string) => {
      const questionCode = currentQuestion.code || `Q${currentIndex + 1}`;
      const currentAnswers = dynamicAnswers[questionCode] || [];

      if (currentQuestion.type === 'multi') {
        // Pour le multi, on met juste à jour les codes pour l'UI
        // On passe un tableau vide [] pour les équivalences car elles seront validées au clic sur "Suivant"
        const nextAnswers = currentAnswers.includes(answerCode)
          ? currentAnswers.filter((code) => code !== answerCode)
          : [...currentAnswers, answerCode];
        
        setDynamicAnswer(questionCode, nextAnswers, []); 
      } else {
        // Mode Single : On utilise la fonction submitAnswer du hook
        // qui contient déjà la logique d'extraction des équivalences
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
  }

  // === MODE STATIQUE (comportement original) ===
  const currentQuestion = QUESTIONS[currentQuestionIndex];
  const totalQuestions = QUESTIONS.length;

  // Track question view quand l'index change (mode statique)
  // useEffect(() => {
  //   if (!isDynamicMode && lastTrackedQuestionIndex.current !== currentQuestionIndex) {
  //     lastTrackedQuestionIndex.current = currentQuestionIndex;
  //     trackQuestionView(currentQuestionIndex, {
  //       question_id: currentQuestion.id,
  //       question_title: currentQuestion.title,
  //       total_questions: totalQuestions,
  //     });
  //   }
  // }, [isDynamicMode, currentQuestionIndex, currentQuestion, totalQuestions]);

  const handleSelectAnswer = (answerId: string, autoAdvance?: boolean) => {
    const currentAnswers = userAnswers[currentQuestion.id] || [];

    if (currentQuestion.multiSelect) {
      // Toggle selection for multi-select
      if (currentAnswers.includes(answerId)) {
        setAnswer(currentQuestion.id, currentAnswers.filter((id) => id !== answerId));
      } else {
        setAnswer(currentQuestion.id, [...currentAnswers, answerId]);
      }
    } else {
      // Single select - replace and auto-advance
      setAnswer(currentQuestion.id, [answerId]);

      // Auto-advance after a short delay for visual feedback
      if (autoAdvance) {
        setTimeout(() => {
          handleNext();
        }, 300);
      }
    }
  };

  const handleOtherTextChange = (text: string) => {
    setOtherText(currentQuestion.id, text);
  };

  const handleNext = () => {
    if (currentQuestionIndex < totalQuestions - 1) {
      // La vue de la question suivante sera trackée automatiquement
      setCurrentQuestionIndex((prev) => prev + 1);
    } else {
      // All questions answered, proceed to selection
      const timeSpent = startTime ? Math.round((Date.now() - startTime) / 1000) : 0;
      trackGTMQuestionnaireComplete(totalQuestions, timeSpent);
      onComplete(userAnswers);
    }
  };

  const handleBack = () => {
    if (currentQuestionIndex > 0) {
      setCurrentQuestionIndex((prev) => prev - 1);
    }
  };

  // Calculate progress: each question is a portion of step 1 (0-33%)
  const questionProgress = ((currentQuestionIndex + 1) / totalQuestions) * 33;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      <ProgressHeader
        steps={STEPS}
        currentStep={1}
        progress={questionProgress}
      />

      <div className="flex-1 overflow-y-auto">
        <QuestionScreen
          question={currentQuestion}
          currentIndex={currentQuestionIndex}
          totalQuestions={totalQuestions}
          selectedAnswers={userAnswers[currentQuestion.id] || []}
          otherText={otherTexts[currentQuestion.id] || ""}
          onSelectAnswer={handleSelectAnswer}
          onOtherTextChange={handleOtherTextChange}
          onNext={handleNext}
          onBack={handleBack}
          isFirst={currentQuestionIndex === 0}
          isLast={currentQuestionIndex === totalQuestions - 1}
        />
      </div>
    </div>
  );
};

export default NeedsQuestionnaire;
