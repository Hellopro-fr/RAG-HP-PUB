'use client';

import { useEffect, useRef } from "react";
import Image from "next/image";
// DISABLED: ProgressHeader remplacé par un header simplifié (logo seul) pour l'étape questionnaire
// import ProgressHeader from "./ProgressHeader";
import QuestionnaireProgressBar from "./QuestionnaireProgressBar";
import QuestionScreen from "./QuestionScreen";
import { getAssetPath } from "@/lib/utils";

const hpLogo = getAssetPath("/images/hp-logo.svg");
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

// DISABLED: STEPS n'est plus utilisé ici — le header questionnaire est simplifié (logo seul)
// const STEPS = [
//   { id: 1, label: "Votre besoin" },
//   { id: 2, label: "Sélection" },
//   { id: 3, label: "Demande de devis" },
// ];

const NeedsQuestionnaire = ({ onComplete, rubriqueId }: NeedsQuestionnaireProps) => {
  // Store Zustand pour persistance dans sessionStorage
  const {
    dynamicAnswers,
    setDynamicAnswer,
    setStartTime,
    startTime,
    categoryName,
  } = useFlowStore();

  // Hook pour le questionnaire dynamique
  const dynamicQuestionnaire = useDynamicQuestionnaire(rubriqueId || '');

  // Si pas de rubriqueId, afficher une erreur
  if (!rubriqueId) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col bg-background">
        {/* Header simplifié — logo seul */}
        <div className="px-4 py-2.5 sm:px-6 border-b border-border">
          <Image src={hpLogo} alt="Hellopro" width={120} height={28} className="h-6 sm:h-7 w-auto" />
        </div>        
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
  // Ref pour savoir si le questionnaire etait deja complet au montage (retour navigateur)
  const wasAlreadyCompleteOnMount = useRef<boolean | null>(null);
  // Ref pour bloquer la redirection apres un reset (evite la race condition)
  const hasJustReset = useRef(false);

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

  // Mettre à jour le contexte quand categoryName devient disponible (chargé via API)
  useEffect(() => {
    if (categoryName) {
      setFunnelContext({
        'product.category5': categoryName,
      });
    }
  }, [categoryName]);

  // Quand le questionnaire dynamique est terminé
  useEffect(() => {
    // Attendre que les données soient chargées avant d'évaluer l'état de complétion
    if (dynamicQuestionnaire.isLoading) return;

    // Premier rendu: memoriser si le questionnaire etait deja complet (retour navigateur)
    if (wasAlreadyCompleteOnMount.current === null) {
      wasAlreadyCompleteOnMount.current = dynamicQuestionnaire.isComplete;
      // Si deja complet au montage, aller a la derniere question (retour navigateur)
      // Les reponses sont conservees dans le store
      if (wasAlreadyCompleteOnMount.current) {
        hasJustReset.current = true;
        dynamicQuestionnaire.goToLastQuestion();
        // Reinitialiser le flag pour permettre la prochaine completion
        wasAlreadyCompleteOnMount.current = false;
        return;
      }
    }

    // Bloquer la redirection juste apres un goToLastQuestion (evite race condition)
    if (hasJustReset.current) {
      hasJustReset.current = false;
      return;
    }

    // Rediriger quand le questionnaire est termine
    if (dynamicQuestionnaire.isComplete) {
      const timeSpent = startTime ? Math.round((Date.now() - startTime) / 1000) : 0;
      trackGTMQuestionnaireComplete(dynamicQuestionnaire.progress.total, timeSpent);
      onComplete(dynamicAnswers);
    }
  }, [dynamicQuestionnaire.isComplete, dynamicQuestionnaire.isLoading, dynamicQuestionnaire.progress.total, dynamicAnswers, onComplete, startTime, dynamicQuestionnaire.goToLastQuestion]);

  // Hook de tracking de vue de question
  useEffect(() => {
    if (dynamicQuestionnaire.currentQuestion && lastTrackedQuestionIndex.current !== dynamicQuestionnaire.currentIndex) {
      lastTrackedQuestionIndex.current = dynamicQuestionnaire.currentIndex;
      trackQuestionView(dynamicQuestionnaire.currentIndex);
    }
  }, [dynamicQuestionnaire.currentIndex, dynamicQuestionnaire.currentQuestion]);

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

  // Refs pour eviter les stale closures dans le handler popstate (pattern comme SupplierSelectionModal)
  const prevIndexRef = useRef(currentIndex);
  const currentIndexRef = useRef(currentIndex);
  const goBackRef = useRef(goBack);
  const isHandlingPopstateRef = useRef(false); // Debounce pour Safari
  const isMountedRef = useRef(false); // Flag pour ignorer les popstate pendant le montage

  // Garder les refs synchronisees
  useEffect(() => { currentIndexRef.current = currentIndex; }, [currentIndex]);
  useEffect(() => { goBackRef.current = goBack; }, [goBack]);

  // Intercepter le bouton retour navigateur pour revenir a la question precedente
  useEffect(() => {
    // Pousser un etat dans l'historique seulement quand on avance (pas quand on recule)
    if (currentIndex > prevIndexRef.current) {
      window.history.pushState({ questionIndex: currentIndex }, '');
    }
    prevIndexRef.current = currentIndex;
  }, [currentIndex]);

  // Ecouter les evenements popstate separement (une seule fois, utilise les refs)
  useEffect(() => {
    // Delai avant d'activer le handler pour eviter les popstate parasites au montage (Safari)
    const mountTimeout = setTimeout(() => {
      isMountedRef.current = true;
    }, 50);

    const handlePopState = () => {
      // Ignorer les popstate pendant le montage initial
      if (!isMountedRef.current) return;

      // Debounce pour eviter les double-declenchements sur Safari
      if (isHandlingPopstateRef.current) return;
      isHandlingPopstateRef.current = true;

      // Si on peut revenir en arriere dans le questionnaire, le faire
      if (currentIndexRef.current > 0) {
        goBackRef.current();
      }
      // Sinon, laisser le navigateur faire son comportement par defaut (quitter)

      // Reset le debounce apres un court delai
      setTimeout(() => {
        isHandlingPopstateRef.current = false;
      }, 100);
    };

    window.addEventListener('popstate', handlePopState);

    return () => {
      clearTimeout(mountTimeout);
      isMountedRef.current = false;
      window.removeEventListener('popstate', handlePopState);
    };
  }, []); // Dependency array vide - le listener ne se reinstalle plus

  const LoadingScreen = ({ progress = 0 }: { progress?: number }) => (
      <div className="fixed inset-0 z-50 flex flex-col bg-background">
        {/* Header simplifié — logo seul */}
        <div className="px-4 py-2.5 sm:px-6 border-b border-border">
          <Image src={hpLogo} alt="Hellopro" width={120} height={28} className="h-6 sm:h-7 w-auto" />
        </div>       
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
          {/* Header simplifié — logo seul */}
        <div className="px-4 py-2.5 sm:px-6 border-b border-border">
          <Image src={hpLogo} alt="Hellopro" width={120} height={28} className="h-6 sm:h-7 w-auto" />
        </div>         
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
          {/* Header simplifié — logo seul */}
        <div className="px-4 py-2.5 sm:px-6 border-b border-border">
          <Image src={hpLogo} alt="Hellopro" width={120} height={28} className="h-6 sm:h-7 w-auto" />
        </div>          
          <div className="flex-1 flex items-center justify-center">
            <p className="text-muted-foreground">Aucune question disponible</p>
          </div>
        </div>
      );
    }

    // DISABLED: questionProgress n'est plus utilisé — remplacé par QuestionnaireProgressBar
    // const questionProgress = progress.percent * 0.33;

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
      bulleAide: currentQuestion.bulleAide ?? null,
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
        {/* Header simplifié — logo seul */}
        <div className="px-4 py-2.5 sm:px-6 border-b border-border">
          <Image src={hpLogo} alt="Hellopro" width={120} height={28} className="h-6 sm:h-7 w-auto" />
        </div>
        <QuestionnaireProgressBar
          categoryName={categoryName || ""}
          currentIndex={currentIndex}
          totalQuestions={progress.total}
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
