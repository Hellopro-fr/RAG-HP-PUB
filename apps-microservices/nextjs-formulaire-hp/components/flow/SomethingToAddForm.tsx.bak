'use client';

import { ArrowRight, Paperclip, X, Mic, MicOff, ArrowLeft, Send, Shield, Clock, CheckCircle } from "lucide-react";
import { useState, useRef, useEffect, useMemo } from "react";
import ProgressHeader from "./ProgressHeader";
import CountryCodeSelect from "./CountryCodeSelect";
import { useBuyerCheck } from "@/hooks/api";
import { useFlowStore } from "@/lib/stores/flow-store";
import { ContactFormData } from "@/types";
import PhoneInput from "./PhoneInput";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { trackCustomNeedPageView, trackCustomNeedContactView, setFlowType } from "@/lib/analytics";

// Mock list of existing buyers in database
const EXISTING_BUYERS = [
  "jean.dupont@entreprise.fr",
  "marie.martin@societe.com",
  "contact@hellopro.fr",
  "acheteur@garage-martin.fr",
];

interface SomethingToAddFormProps {
  onNext: () => void;
  onBack: () => void;
}

const STEPS = [
  { id: 1, label: "Votre besoin" },
  { id: 2, label: "Vos coordonnées" },
];

const SomethingToAddForm = ({ onNext, onBack }: SomethingToAddFormProps) => {

   const {
    setContactData,
    files: filesStore,
    addFilesStore,
    flowType,
    setFlowType: setStoreFlowType
  } = useFlowStore();

  const [currentStep, setCurrentStep] = useState(1);
  const [description, setDescription] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [isListening, setIsListening] = useState(false);
  const [formData, setFormData] = useState<ContactFormData>({
    email: "",
    isKnown: false,
    civility: "",
    firstName: "",
    lastName: "",
    countryCode: "+33",
    id_pays_tel: 1, // France par défaut
    phone: "",
  });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);
  

  // Ref pour éviter les doubles appels en StrictMode
  const hasTrackedPageView = useRef(false);

  // Track page view au montage et définir flowType si pas déjà défini
  useEffect(() => {
    if (!hasTrackedPageView.current) {
      hasTrackedPageView.current = true;

      // Si flowType n'est pas défini (redirection automatique car pas assez de produits)
      // Le définir comme 'pas_assez_produits'
      // Si déjà 'pas_trouve_recherchez' (clic "pas trouvé"), on garde cette valeur
      if (!flowType) {
        setStoreFlowType('pas_assez_produits');
        setFlowType('pas_assez_produits');
      }

      trackCustomNeedPageView();
    }
  }, [flowType, setStoreFlowType]);

  // Check if email is from an existing buyer
  // const isExistingBuyer = useMemo(() => {
  //   if (!formData.email || formData.email.length < 5) return false;
  //   return EXISTING_BUYERS.some(
  //     (email) => email.toLowerCase() === formData.email.toLowerCase()
  //   );
  // }, [formData.email]);

  // Check if email is valid format
  const isEmailValid = useMemo(() => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(formData.email);
  }, [formData.email]);

    // Dynamic buyer check via API
  const { data: buyerCheckResult } = useBuyerCheck(
    {
      email     : formData.email,
      rubriqueId: '2001661',
    },
    isEmailValid
  );

  const isExistingBuyer = buyerCheckResult?.isDuplicate || false;
  const isKnownBuyer    = buyerCheckResult?.isKnown || false;

  useEffect(() => {
      let updatedData: ContactFormData | null = null;
  
      // 1. On vérifie si l'acheteur est reconnu et si on a les données
      if (isKnownBuyer && buyerCheckResult?.infoBuyer) {
        const info = buyerCheckResult.infoBuyer as any;
  
        // 2. On prépare l'objet complet avec les clés de votre interface ContactFormData
        updatedData = {
          ...formData,                   // On garde le message et les autres champs
          email    : formData.email,      // L'email déjà saisi
          isKnown  : true,
          firstName: info.prenom || "",
          lastName : info.nom || "",
          phone    : info.tel || "",
        
        };
              
      }else{
        updatedData = {
          ...formData,
          email      : formData.email,
          isKnown    : false,
          firstName  : "",
          lastName   : "",
          phone      : "",
          countryCode: formData.countryCode || "+33",
          id_pays_tel: formData.id_pays_tel || 1,
        };
      }
  
      if (updatedData) {
        setFormData(updatedData);
      }
      
      // On ne déclenche cet effet que lorsque 'isKnownBuyer' ou 'infoBuyer' change
    }, [isKnownBuyer, buyerCheckResult?.infoBuyer]);  

  // Show additional fields only if email is valid and not an existing buyer
  const showAdditionalFields = isEmailValid && !isKnownBuyer;

  // Form is valid only if civility is selected when additional fields are shown
  const isFormValid = !showAdditionalFields || !!formData.civility;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files);
      setFiles(prev => [...prev, ...newFiles]);

      // 2. Mise à jour du store (pour la persistance/soumission)
      addFilesStore(newFiles);

      e.target.value = '';
    }
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isFormValid) return;

    console.log("Form submitted:", { description, fileName, ...formData });

     const finalData = { 
      ...formData, 
      files: filesStore, // On s'assure que les fichiers du store sont inclus
      message: description
    };

    finalData.files.forEach((file, index) => {
      console.log(`Fichier ${index}:`, {
        nom: file.name,
        taille: file.size,
        type: file.type
      });
    });

    setContactData(finalData);
    onNext();
  };

  // Initialize Speech Recognition
  useEffect(() => {
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
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      {/* Header */}
      <ProgressHeader
        steps={STEPS}
        currentStep={currentStep}
        progress={currentStep === 1 ? 50 : 90}
      />

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
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

                {/* Title */}
                <div className="text-center">
                  <h2 className="text-2xl font-bold text-foreground">
                    Décrivez votre besoin
                  </h2>
                  <p className="mt-1 text-muted-foreground">
                    Précisez des informations complémentaires pour affiner votre recherche
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
                        Vos précisions{" "}
                        <span className="text-muted-foreground">(optionnel)</span>
                      </label>
                      <button
                        type="button"
                        onClick={toggleListening}
                        className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-all shadow-sm ${
                          isListening
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
                        className={`w-full rounded-lg border bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all resize-none ${
                          isListening ? "border-red-400 ring-2 ring-red-100" : "border-input"
                        }`}
                        placeholder="Ex: Je souhaite aussi pouvoir lever des véhicules électriques, j'ai besoin d'une formation..."
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
                        {files.length > 0 
                          ? files.map(f => f.name).join(", ") 
                          : "Ajouter un document (cahier des charges, photo...)"
                        }
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
                  <div className="flex flex-col sm:flex-row items-center gap-3 pt-4">
                    <button
                      onClick={onBack}
                      className="order-2 sm:order-1 w-full sm:w-auto rounded-lg border-2 border-border bg-background px-6 py-3 text-sm font-medium text-foreground hover:bg-muted transition-colors"
                    >
                      Annuler
                    </button>
                    <button
                      onClick={goToNextStep}
                      className="order-1 sm:order-2 w-full sm:w-auto flex-1 sm:flex-none rounded-lg bg-accent px-8 py-3 text-base font-semibold text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25 transition-all flex items-center justify-center gap-2"
                    >
                      Suivant
                      <ArrowRight className="h-5 w-5" />
                    </button>
                  </div>
                </div>
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
                    {isKnownBuyer && (
                      <div className="mt-2 flex items-center gap-2 text-sm text-green-600">
                        <CheckCircle className="h-4 w-4" />
                        <span>Nous vous avons reconnu ! Vos informations sont pré-enregistrées.</span>
                      </div>
                    )}
                    {isExistingBuyer && buyerCheckResult?.message && (
                      <div className="mt-2 flex items-center gap-2 text-sm text-orange-600">
                        <Shield className="h-4 w-4" />
                        <span>{buyerCheckResult.message}</span>
                      </div>
                    )}
                  </div>

                  {/* Additional fields - only shown if email is valid and not existing buyer */}
                  {showAdditionalFields && (
                    <>
                      {/* Civilité */}
                      <div>
                        <label className="block text-sm font-medium text-foreground mb-2">
                          Civilité *
                        </label>
                        <RadioGroup
                          value={formData.civility}
                          onValueChange={(value) => setFormData({ ...formData, civility: value })}
                          className="flex gap-6"
                        >
                          <div className="flex items-center space-x-2">
                            <RadioGroupItem value="mr" id="civility-mr-staf" />
                            <Label htmlFor="civility-mr-staf" className="cursor-pointer">Mr</Label>
                          </div>
                          <div className="flex items-center space-x-2">
                            <RadioGroupItem value="mme" id="civility-mme-staf" />
                            <Label htmlFor="civility-mme-staf" className="cursor-pointer">Mme</Label>
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
                        </div>
                      </div>

                      <div>
                        <label
                          htmlFor="phone"
                          className="block text-sm font-medium text-foreground mb-1.5"
                        >
                          Téléphone *
                        </label>                        
                        <PhoneInput
                          value={formData.phone}
                          countryCode={formData.countryCode || "+33"}
                          countryId={formData.id_pays_tel}
                          onValueChange={(phone) => setFormData((prev) => ({ ...prev, phone }))}
                          onCountryCodeChange={(code) => setFormData((prev) => ({ ...prev, countryCode: code }))}
                          onCountryIdChange={(id) => setFormData((prev) => ({ ...prev, id_pays_tel: id }))}
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
                    disabled={!isFormValid}
                    className="w-full rounded-xl bg-accent py-4 text-lg font-semibold text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25 transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Send className="h-5 w-5" />
                    Envoyer ma demande
                  </button>
                </form>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SomethingToAddForm;
