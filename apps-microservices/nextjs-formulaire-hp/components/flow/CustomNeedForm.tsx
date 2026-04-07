'use client';

import { ArrowLeft, ArrowRight, Paperclip, Send, UserCheck, X, Mic, MicOff, Shield, Clock, CheckCircle } from "lucide-react";
import { useState, useRef, useEffect, useMemo } from "react";
import PhoneInput from "./PhoneInput";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { trackCustomNeedPageView, trackCustomNeedContactView, trackFormValidationErrors } from "@/lib/analytics";
import { useLeadSubmission } from "@/hooks/api/useLeadSubmission";
import { validatePhoneNumber } from "@/lib/utils/phone-validation";
import { toast } from "@/hooks/use-toast";
import { useFlowStore, FLOW_SUBMISSION_COMPLETED_KEY, FLOW_ORIGINAL_TOKEN_KEY } from "@/lib/stores/flow-store";
import { buildPriceTrackingPayload } from "@/lib/utils/build-price-tracking-payload";
import { useDbTracking } from "@/hooks/tracking/useDbTracking";
import { ContactFormData } from "@/types";
import { useBuyerCheck } from "@/hooks/api";


export type CustomNeedVariant = 'budget' | 'initial';

interface CustomNeedFormProps {
  onBack: () => void;
  onContactComplete?: (isExistingBuyer: boolean) => void;
  variant?: CustomNeedVariant;
}

const CustomNeedForm = ({ onBack, onContactComplete, variant = 'initial' }: CustomNeedFormProps) => {
  const {
    setContactData,
    flowType,
    profileData,
    userAnswers,
    selectedSupplierIds,
    categoryId,
    files: filesStore,
    setFilesStore,
    addFilesStore,
    priceEstimation
  } = useFlowStore();

  const [currentStep, setCurrentStep] = useState(1);
  const [description, setDescription] = useState("");
  const [budget, setBudget] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [isListening, setIsListening] = useState(false);

  const [formData, setFormData] = useState<ContactFormData>({
    email: "",
    isKnown: false,
    civility: "",
    firstName: "",
    lastName: "",
    company: profileData?.company?.name || profileData?.companyName || "",
    countryCode: "+33",
    id_pays_tel: 1, // France par défaut
    phone: "",
    message: "",
  });


  const [errors, setErrors] = useState<Partial<Record<keyof typeof formData, string>>>({});
  const [files, setFiles] = useState<File[]>([]);
  const [showFallbackRedirect, setShowFallbackRedirect] = useState<boolean>(false);
  const fallbackMessageRef = useRef<HTMLParagraphElement>(null);

  const leadSubmission = useLeadSubmission();

  // Gérer la redirection fallback si l'API ne retourne pas une URL externe
  useEffect(() => {
    if (leadSubmission.isSuccess && leadSubmission.data?.data) {
      const { isExternalRedirect, fallbackUrl } = leadSubmission.data.data;
      if (!isExternalRedirect && fallbackUrl) {
        // Marquer la soumission comme complétée IMMÉDIATEMENT (pas dans le setTimeout!)
        try {
          const originalToken = typeof window !== 'undefined'
            ? sessionStorage.getItem(FLOW_ORIGINAL_TOKEN_KEY)
            : undefined;

          const submissionData = {
            timestamp: Date.now(),
            originalToken: originalToken || undefined,
            categoryId: categoryId,
            expiresAt: Date.now() + (48 * 60 * 60 * 1000), // 48h (sécurité)
          };

          localStorage.setItem(
            FLOW_SUBMISSION_COMPLETED_KEY,
            JSON.stringify(submissionData)
          );
        } catch (e) {
          console.error('[CustomNeedForm] ❌ Failed to set submission flag:', e);
        }

        // Afficher le message d'erreur et rediriger après 2 secondes
        setShowFallbackRedirect(true);
        // Scroll vers le message après un court délai pour laisser le rendu se faire
        setTimeout(() => {
          fallbackMessageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 100);
        const timer = setTimeout(() => {
          // Redirection vers page feuille (quitte Next.js)
          window.location.href = fallbackUrl;
        }, 2000);
        return () => clearTimeout(timer);
      }
    }
  }, [leadSubmission.isSuccess, leadSubmission.data, categoryId]);
  const { trackDbEvent } = useDbTracking();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);

  // Check if email is valid format
  const isEmailValid = useMemo(() => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(formData.email);
  }, [formData.email]);

  const { data: buyerCheckResult, isLoading: isCheckingBuyer } = useBuyerCheck(
    {
      email: formData.email,
      rubriqueId: categoryId?.toString(),
    },
    isEmailValid
  );

  const isExistingBuyer = buyerCheckResult?.isDuplicate || false;
  const isKnownBuyer = buyerCheckResult?.isKnown || false;

  useEffect(() => {
    let updatedData: ContactFormData | null = null;

    // 1. On vérifie si l'acheteur est reconnu et si on a les données
    if (isKnownBuyer && buyerCheckResult?.infoBuyer) {
      const info = buyerCheckResult.infoBuyer as any;

      // 2. On prépare l'objet complet avec les clés de votre interface ContactFormData
      updatedData = {
        ...formData,                   // On garde le message et les autres champs
        email: formData.email,      // L'email déjà saisi
        isKnown: true,
        firstName: info.prenom || "",
        lastName: info.nom || "",
        phone: info.tel || "",
        civility: info.cv || "",
        id_acheteur: info.id || undefined,
      };

    } else {
      updatedData = {
        ...formData,
        email: formData.email,
        isKnown: false,
        firstName: "",
        lastName: "",
        phone: "",
        countryCode: formData.countryCode || "+33",
        id_pays_tel: formData.id_pays_tel || 1,
        id_acheteur: undefined,
      };
    }

    if (updatedData) {
      setFormData(updatedData);
    }

    // On ne déclenche cet effet que lorsque 'isKnownBuyer' ou 'infoBuyer' change
  }, [isKnownBuyer, buyerCheckResult?.infoBuyer]);

  // Show additional fields only if email is valid and not an existing buyer
  // AND we are not currently checking (to avoid flickering)
  const showAdditionalFields = isEmailValid && !isKnownBuyer && !isCheckingBuyer;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files);
      setFiles(prev => [...prev, ...newFiles]);
      setFileName(newFiles[0].name);
      // Update store if helper available
      if (addFilesStore) addFilesStore(newFiles);
      e.target.value = '';
    }
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const isFormValid = !showAdditionalFields || !!formData.civility;

  const validateForm = (): boolean => {
    const newErrors: Partial<Record<keyof typeof formData, string>> = {};

    if (!formData.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = "Email invalide";
    }
    if (!formData.civility) {
      newErrors.civility = "Civilité requise";
    }
    if (!formData.firstName.trim()) {
      newErrors.firstName = "Prénom requis";
    }
    if (!formData.lastName.trim()) {
      newErrors.lastName = "Nom requis";
    }

    const phoneValidation = validatePhoneNumber(formData.phone, formData.countryCode || "+33");
    if (!phoneValidation.isValid) {
      newErrors.phone = phoneValidation.error || "Téléphone invalide";
    }

    setErrors(newErrors);

    if (Object.keys(newErrors).length > 0) {
      const errorList = Object.entries(newErrors).map(([field, message]) => ({
        field,
        type: field === 'email' || field === 'phone' ? 'invalid_format' : 'required',
        message: message || '',
      }));
      trackFormValidationErrors(errorList.length, errorList);

      if (newErrors.civility) {
        toast({
          variant: "destructive",
          title: "Champ requis",
          description: newErrors.civility,
        });
      }
    }

    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!(isKnownBuyer && buyerCheckResult?.infoBuyer)) {
      const isValid = validateForm();
      if (!isValid) return;
    }

    const userKnownStatus = isKnownBuyer ? 'known' as const : 'unknown' as const;

    const finalData: any = {
      ...formData,
      files  : filesStore || files,
      message: description,
      budget : budget,
    };

    finalData.files = finalData.files || files;

    setContactData(finalData);

    // Tracking DB - Something to add form submission
    trackDbEvent('contact', 'form_submit_custom_need', {
      email: finalData.email,
      is_known_buyer: isKnownBuyer,
      has_description: !!description,
      has_files: (finalData.files?.length || 0) > 0,
      files_count: finalData.files?.length || 0,
      flow_type: flowType,
      price_estimation: buildPriceTrackingPayload(priceEstimation),
    }, categoryId, 1);

    // Si acheteur connu: soumettre le lead directement
    // Si acheteur inconnu: aller au ProfileTypeStep (le lead sera soumis après)
    if (isKnownBuyer) {
      leadSubmission.mutate({
        contact: finalData,
        profile: profileData!,
        answers: userAnswers,
        selectedSupplierIds: selectedSupplierIds,
        submittedAt: new Date().toISOString(),
        userKnownStatus,
        categoryId: categoryId?.toString(),
        source: 1, // AO
      }, {
        onSuccess: () => {
          onContactComplete?.(true);
        }
      });
    } else {
      // Unknown buyer: go to ProfileTypeStep
      onContactComplete?.(false);
    }
  };

  // Ref pour éviter les doubles appels en StrictMode
  const hasTrackedView = useRef(false);

  // Track view on mount + Initialize Speech Recognition
  useEffect(() => {
    // Track view (only once)
    if (!hasTrackedView.current) {
      hasTrackedView.current = true;
      trackCustomNeedPageView();
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = true;
      recognitionRef.current.interimResults = true;
      recognitionRef.current.lang = 'fr-FR';

      recognitionRef.current.onresult = (event: any) => {
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalTranscript += transcript;
          }
        }

        if (finalTranscript) {
          setDescription(prev => prev + (prev ? ' ' : '') + finalTranscript);
        }
      };

      recognitionRef.current.onerror = (event: any) => {
        console.error('Speech recognition error:', event.error);
        setIsListening(false);
      };

      recognitionRef.current.onend = () => {
        setIsListening(false);
      };
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, []);

  const toggleListening = () => {
    if (!recognitionRef.current) {
      alert("La reconnaissance vocale n'est pas supportée par votre navigateur");
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      recognitionRef.current.start();
      setIsListening(true);
    }
  };

  const goToNextStep = () => {
    setCurrentStep(2);
    trackCustomNeedContactView();
  };

  const goToPreviousStep = () => {
    setCurrentStep(1);
  };

  return (
    <div className="p-6 lg:p-10">
      <div className="mx-auto max-w-2xl space-y-6">
        {currentStep === 1 ? (
          <>
            {/* Step 1: Votre besoin */}
            {/* Header with back button */}
            <div className="flex items-center justify-between">
              <button
                onClick={onBack}
                className="flex items-center gap-2 rounded-lg border-2 border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-muted transition-colors"
              >
                <X className="h-4 w-4" />
                Annuler
              </button>
            </div>

            {/* ===== VARIANT: BUDGET ===== */}
            {variant === 'budget' && (
              <>
                {/* Title */}
                <div className="text-center">
                  <h2 className="text-2xl font-bold text-foreground">
                    Ajustez votre recherche
                  </h2>
                  <p className="mt-1 text-muted-foreground">
                    Nous allons rechercher un fournisseur adapté à votre budget et vos contraintes.
                  </p>
                </div>

                {/* Form */}
                <div className="space-y-5">
                  {/* Budget input */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label
                        htmlFor="budget"
                        className="block text-sm font-medium text-foreground"
                      >
                        Budget souhaité *
                      </label>
                    </div>
                    <div className="relative">
                      <input
                        id="budget"
                        value={budget}
                        onChange={(e) => setBudget(e.target.value)}
                        className={`w-full rounded-lg border bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all resize-none ${isListening ? "border-red-400 ring-2 ring-red-100" : "border-input"
                          }`}
                        placeholder="Ex: 2 000 € – 3 000 € HT"
                      />
                      {isListening && (
                        <div className="absolute bottom-3 right-3 flex items-center gap-1.5 text-xs text-red-500">
                          <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
                          </span>
                          Écoute en cours...
                        </div>
                      )}
                    </div>
                  </div>
                  {/* Reassurance */}
                  <div className="flex items-start gap-3 rounded-xl bg-primary/5 border border-primary/10 p-4">
                    <UserCheck className="h-5 w-5 shrink-0 text-primary mt-0.5" />
                    <p className="text-sm text-foreground/80">
                      Nos experts vont rechercher un fournisseur adapté à votre budget et vos besoins spécifiques.
                    </p>
                  </div>
                  {/* Description */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label
                        htmlFor="description"
                        className="block text-sm font-medium text-foreground"
                      >
                        Quelque chose à ajouter ? <span className="text-muted-foreground">(optionnel)</span>
                      </label>
                      <button
                        type="button"
                        onClick={toggleListening}
                        className={`hidden flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-all shadow-sm ${isListening
                          ? "bg-red-500 text-white animate-pulse shadow-red-200"
                          : "bg-primary text-primary-foreground hover:bg-primary/90 shadow-primary/20"
                          }`}
                      >
                        {isListening ? (
                          <>
                            <MicOff className="h-4 w-4" />
                            Arrêter
                          </>
                        ) : (
                          <>
                            <Mic className="h-4 w-4" />
                            Dicter
                          </>
                        )}
                      </button>
                    </div>
                    <div className="relative">
                      <textarea
                        id="description"
                        rows={5}
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        className={`w-full rounded-lg border bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all resize-none ${isListening ? "border-red-400 ring-2 ring-red-100" : "border-input"
                          }`}
                        placeholder="Ex: Je cherche du matériel d'occasion, ou j'ai des contraintes spécifiques..."
                      />
                      {isListening && (
                        <div className="absolute bottom-3 right-3 flex items-center gap-1.5 text-xs text-red-500">
                          <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
                          </span>
                          Écoute en cours...
                        </div>
                      )}
                    </div>
                  </div>

                  {/* File upload */}
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1.5">
                      Document complémentaire{" "}
                      <span className="text-muted-foreground">(optionnel)</span>
                    </label>
                    <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border-2 border-dashed border-input bg-background px-4 py-5 text-muted-foreground hover:border-primary/50 hover:bg-secondary/50 transition-all">
                      <Paperclip className="h-5 w-5" />
                      <span className="text-sm">
                        {fileName
                          ? fileName
                          : "Ajouter un document (cahier des charges, photo...)"}
                      </span>
                      <input
                        type="file"
                        className="hidden"
                        onChange={handleFileChange}
                        accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                      />
                    </label>
                  </div>

                  {/* Actions */}
                  <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
                    <button
                      onClick={onBack}
                      className="order-2 sm:order-1 w-full sm:w-auto rounded-lg border-2 border-border bg-background px-6 py-3 text-sm font-medium text-foreground hover:bg-muted transition-colors"
                    >
                      Annuler
                    </button>
                    <button
                      onClick={goToNextStep}
                      disabled={!budget.trim()}
                      className={`order-1 sm:order-2 w-full sm:w-auto flex-1 sm:flex-none rounded-lg px-8 py-3 text-base font-semibold transition-all flex items-center justify-center gap-2 ${budget.trim()
                        ? "bg-accent text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25"
                        : "bg-muted text-muted-foreground cursor-not-allowed"
                        }`}
                    >
                      Suivant
                      <ArrowRight className="h-5 w-5" />
                    </button>
                  </div>
                </div>
              </>
            )}

            {/* ===== VARIANT: INITIAL (pas trouvé ce que vous cherchez) ===== */}
            {variant === 'initial' && (
              <>
                {/* Title */}
                <div className="text-center">
                  <h2 className="text-2xl font-bold text-foreground">
                    Décrivez votre besoin
                  </h2>
                  <p className="mt-1 text-muted-foreground">
                    Votre besoin est unique ? Décrivez-le et nos experts trouveront les
                    fournisseurs qu'il vous faut.
                  </p>
                </div>

                {/* Form */}
                <div className="space-y-5">
                  {/* Description with voice input */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label
                        htmlFor="description"
                        className="block text-sm font-medium text-foreground"
                      >
                        Votre besoin *
                      </label>
                      <button
                        type="button"
                        onClick={toggleListening}
                        className={`hidden flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-all shadow-sm ${isListening
                          ? "bg-red-500 text-white animate-pulse shadow-red-200"
                          : "bg-primary text-primary-foreground hover:bg-primary/90 shadow-primary/20"
                          }`}
                      >
                        {isListening ? (
                          <>
                            <MicOff className="h-4 w-4" />
                            Arrêter
                          </>
                        ) : (
                          <>
                            <Mic className="h-4 w-4" />
                            🎤 Dicter
                          </>
                        )}
                      </button>
                    </div>
                    <div className="relative">
                      <textarea
                        id="description"
                        rows={5}
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        className={`w-full rounded-lg border bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all resize-none ${isListening ? "border-red-400 ring-2 ring-red-100" : "border-input"
                          }`}
                        placeholder="Ex: Je cherche un pont élévateur pour véhicules utilitaires longs, avec hauteur de levée 2m minimum..."
                      />
                      {isListening && (
                        <div className="absolute bottom-3 right-3 flex items-center gap-1.5 text-xs text-red-500">
                          <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
                          </span>
                          Écoute en cours...
                        </div>
                      )}
                    </div>
                  </div>

                  {/* File upload */}
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1.5">
                      Document complémentaire{" "}
                      <span className="text-muted-foreground">(optionnel)</span>
                    </label>
                    <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border-2 border-dashed border-input bg-background px-4 py-5 text-muted-foreground hover:border-primary/50 hover:bg-secondary/50 transition-all">
                      <Paperclip className="h-5 w-5" />
                      <span className="text-sm">
                        {fileName
                          ? fileName
                          : "Ajouter un document (cahier des charges, photo...)"}
                      </span>
                      <input
                        type="file"
                        className="hidden"
                        onChange={handleFileChange}
                        accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                      />
                    </label>
                  </div>

                  {/* Reassurance */}
                  <div className="flex items-start gap-3 rounded-xl bg-primary/5 border border-primary/10 p-4">
                    <UserCheck className="h-5 w-5 shrink-0 text-primary mt-0.5" />
                    <p className="text-sm text-foreground/80">
                      Un expert analysera votre demande et vous proposera les meilleurs
                      fournisseurs sous 24h
                    </p>
                  </div>

                  {/* Actions */}
                  <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
                    <button
                      onClick={onBack}
                      className="order-2 sm:order-1 w-full sm:w-auto rounded-lg border-2 border-border bg-background px-6 py-3 text-sm font-medium text-foreground hover:bg-muted transition-colors"
                    >
                      Annuler
                    </button>
                    <button
                      onClick={goToNextStep}
                      disabled={!description.trim()}
                      className={`order-1 sm:order-2 w-full sm:w-auto flex-1 sm:flex-none rounded-lg px-8 py-3 text-base font-semibold transition-all flex items-center justify-center gap-2 ${description.trim()
                        ? "bg-accent text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25"
                        : "bg-muted text-muted-foreground cursor-not-allowed"
                        }`}
                    >
                      Suivant
                      <ArrowRight className="h-5 w-5" />
                    </button>
                  </div>
                </div>
              </>
            )}
          </>
        ) : (
          <>
            {/* Step 2: Vos coordonnées */}
            {/* Back button */}
            <button
              onClick={goToPreviousStep}
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
              Retour
            </button>

            {/* Title */}
            <div>
              <h2 className="text-2xl font-bold text-foreground">Vos coordonnées</h2>
              <p className="mt-1 text-muted-foreground">
                Recevez des propositions personnalisées sous 48h
              </p>
            </div>

            {/* Info box */}
            <div className="rounded-xl bg-secondary p-4">
              <p className="text-sm text-muted-foreground">
                Un expert analysera votre demande et l'enverra aux meilleurs fournisseurs qui vous répondront sous 48h.
              </p>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label
                  htmlFor="email"
                  className="block text-sm font-medium text-foreground mb-1.5"
                >
                  Email professionnel *
                </label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  required
                  value={formData.email}
                  onChange={handleChange}
                  className="w-full rounded-lg border border-input bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
                  placeholder="vous@entreprise.com"
                />
                {errors.email && <p className="mt-1 text-sm text-destructive">{errors.email}</p>}
                {isKnownBuyer && (
                  <div className="mt-2 flex items-center gap-2 text-sm text-green-600">
                    <CheckCircle className="h-4 w-4" />
                    <span>Nous vous avons reconnu ! Vos informations sont pré-enregistrées.</span>
                  </div>
                )}
              </div>

              {/* Additional fields - only shown if email is valid and not existing buyer */}
              {showAdditionalFields && (
                <>
                  {/* Civilité */}
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1.5">
                      Civilité *
                    </label>
                    <RadioGroup
                      value={formData.civility}
                      onValueChange={(value) => setFormData({ ...formData, civility: value })}
                      className="flex gap-4"
                    >
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="1" id="civility-mr-cnf" />
                        <Label htmlFor="civility-mr-cnf">Monsieur</Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="2" id="civility-mme-cnf" />
                        <Label htmlFor="civility-mme-cnf">Madame</Label>
                      </div>
                    </RadioGroup>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label
                        htmlFor="firstName"
                        className="block text-sm font-medium text-foreground mb-1.5"
                      >
                        Prénom *
                      </label>
                      <input
                        type="text"
                        id="firstName"
                        name="firstName"
                        required
                        value={formData.firstName}
                        onChange={handleChange}
                        className="w-full rounded-lg border border-input bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
                      />
                      {errors.firstName && <p className="mt-1 text-sm text-destructive">{errors.firstName}</p>}
                    </div>
                    <div>
                      <label
                        htmlFor="lastName"
                        className="block text-sm font-medium text-foreground mb-1.5"
                      >
                        Nom *
                      </label>
                      <input
                        type="text"
                        id="lastName"
                        name="lastName"
                        required
                        value={formData.lastName}
                        onChange={handleChange}
                        className="w-full rounded-lg border border-input bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
                      />
                      {errors.lastName && <p className="mt-1 text-sm text-destructive">{errors.lastName}</p>}
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1.5">
                      Téléphone *
                    </label>
                    <PhoneInput
                      value={formData.phone}
                      countryCode={formData.countryCode || "+33"}
                      countryId={formData.id_pays_tel}
                      onValueChange={(phone) => setFormData((prev) => ({ ...prev, phone }))}
                      onCountryCodeChange={(countryCode) => setFormData((prev) => ({ ...prev, countryCode }))}
                      onCountryIdChange={(id_pays_tel) => setFormData((prev) => ({ ...prev, id_pays_tel }))}
                      error={errors.phone}
                      required
                    />
                  </div>
                </>
              )}

              {/* Reassurance */}
              <div className="flex flex-col gap-2 rounded-xl bg-secondary/50 p-4">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Clock className="h-4 w-4 text-primary" />
                  Réponse garantie sous 48h
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Shield className="h-4 w-4 text-primary" />
                  Vos données sont protégées et confidentielles
                </div>
              </div>

              {/* Submit button */}
              <button
                type="submit"
                disabled={!isFormValid || leadSubmission.isPending || leadSubmission.isSuccess}
                className="w-full rounded-xl bg-accent py-4 text-lg font-semibold text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25 transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {(leadSubmission.isPending || leadSubmission.isSuccess) ? (
                  <>
                    <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent-foreground border-t-transparent" />
                    Envoi en cours...
                  </>
                ) : isKnownBuyer ? (
                  <>
                    <Send className="h-5 w-5" />
                    Valider ma demande
                  </>
                ) : (
                  <>
                    Suivant
                    <ArrowRight className="h-5 w-5" />
                  </>
                )}
              </button>

              {leadSubmission.isError && (
                <p className="text-center text-sm text-destructive">
                  Une erreur est survenue. Veuillez réessayer plus tard.
                </p>
              )}

              {showFallbackRedirect && (
                <p ref={fallbackMessageRef} className="text-center text-sm text-destructive">
                  Une erreur est survenue. Vous allez être redirigé vers la catégorie.
                </p>
              )}
            </form>
          </>
        )}
      </div>
    </div>
  );
};

export default CustomNeedForm;
