'use client';

import { ArrowLeft, ArrowRight, Send, Shield, Clock, CheckCircle } from "lucide-react";
import { useState, useMemo, useEffect } from "react";
import PhoneInput from "./PhoneInput";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import ProgressHeader from "./ProgressHeader";
import { useLeadSubmission } from "@/hooks/api/useLeadSubmission";
import { useFlowStore } from "@/lib/stores/flow-store";
import { buildPriceTrackingPayload } from "@/lib/utils/build-price-tracking-payload";
import { validatePhoneNumber } from "@/lib/utils/phone-validation";
import { toast } from "@/hooks/use-toast";
import { trackFormValidationErrors } from "@/lib/analytics";
import type { ContactFormData } from "@/types";
import { useDbTracking } from "@/hooks/tracking/useDbTracking";
import { useBuyerCheck } from "@/hooks/api";

interface ContactFormSimpleProps {
  onBack: () => void;
  onContactComplete?: (isExistingBuyer: boolean) => void;
}

const STEPS = [
  { id: 1, label: "Votre besoin" },
  { id: 2, label: "Précisions" },
  { id: 3, label: "Vos coordonnées" },
];

const ContactFormSimple = ({ onBack, onContactComplete }: ContactFormSimpleProps) => {
  const [formData, setFormData] = useState<ContactFormData>({
    email: "",
    isKnown: false,
    civility: "",
    firstName: "",
    lastName: "",
    company: "",
    countryCode: "+33",
    id_pays_tel: 1, // France par défaut
    phone: "",
    message: "",
  });

  const [errors, setErrors] = useState<Partial<Record<keyof ContactFormData, string>>>({});

  // Check if email is valid format
  const isEmailValid = useMemo(() => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(formData.email);
  }, [formData.email]);

  const leadSubmission = useLeadSubmission();
  const { profileData, userAnswers, selectedSupplierIds, setContactData, categoryId, priceEstimation } = useFlowStore();
  const { trackDbEvent } = useDbTracking();

   // Dynamic buyer check via API
   const { data: buyerCheckResult, isLoading: isCheckingBuyer } = useBuyerCheck(
    {
      email     : formData.email,
      rubriqueId: categoryId?.toString(),
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
        civility: info.cv || "",
        company  : info.societe || formData.company || "",
        id_acheteur: info.id || undefined,
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
        id_acheteur: undefined,
      };
    }

    if (updatedData) {
      setFormData(updatedData);
    }
    
    // On ne déclenche cet effet que lorsque 'isKnownBuyer' ou 'infoBuyer' change
  }, [isKnownBuyer, buyerCheckResult?.infoBuyer]);  


  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
    // Clear error when field is modified
    if (errors[name as keyof ContactFormData]) {
      setErrors({ ...errors, [name]: undefined });
    }
  };

  // Show additional fields only if email is valid and not an existing buyer
  // AND we are not currently checking (to avoid flickering)
  const showAdditionalFields = isEmailValid && !isKnownBuyer && !isCheckingBuyer;

  const isFormValid = !showAdditionalFields || !!formData.civility;

  const validateForm = (): boolean => {
    const newErrors: Partial<Record<keyof ContactFormData, string>> = {};

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

    // Validation téléphone
    const phoneValidation = validatePhoneNumber(formData.phone, formData.countryCode || "+33");
    if (!phoneValidation.isValid) {
      newErrors.phone = phoneValidation.error || "Téléphone invalide";
    }

    setErrors(newErrors);

    // Track validation errors if any
    if (Object.keys(newErrors).length > 0) {
      const errorList = Object.entries(newErrors).map(([field, message]) => ({
        field,
        type: field === 'email' || field === 'phone' ? 'invalid_format' : 'required',
        message: message || '',
      }));
      trackFormValidationErrors(errorList.length, errorList);

      // Toast pour les erreurs non visibles (ex: civilité en haut du formulaire)
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

    // Si utilisateur connu (reconnu localement), on skip la validation; sinon on valide le formulaire
    if (!(isKnownBuyer && buyerCheckResult?.infoBuyer)) {
      const isValid = validateForm();
      if (!isValid) return;
    }

    const userKnownStatus = isKnownBuyer ? 'known' as const : 'unknown' as const;

    const finalData: ContactFormData = {
      ...formData,
      isKnown: isKnownBuyer,
    };

    setContactData(finalData);

    // Tracking DB - Contact form submission (simple)
    trackDbEvent('contact', 'form_submit_simple', {
      email: finalData.email,
      is_known_buyer: isKnownBuyer,
      has_message: !!finalData.message,
      has_files: false,
      files_count: 0,
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

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      {/* Header */}
      <ProgressHeader
        steps={STEPS}
        currentStep={3}
        progress={90}
      />

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-6 space-y-6">
          {/* Back button */}
          <button
            onClick={onBack}
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Retour
          </button>

          {/* Centered content container */}
          <div className="mx-auto max-w-xl space-y-6">
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
                  Email professionnel * (TODO: pré-rempli si connu)
                </label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  required
                  value={formData.email}
                  onChange={handleChange}
                  className={`w-full rounded-lg border ${errors.email ? 'border-destructive' : 'border-input'} bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 ${errors.email ? 'focus:border-destructive focus:ring-destructive/20' : 'focus:border-primary focus:ring-primary/20'} transition-all`}
                  placeholder="vous@entreprise.com"
                />
                {errors.email && <p className="mt-1 text-sm text-destructive">{errors.email}</p>}
                {isExistingBuyer && (
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
                        <RadioGroupItem value="mr" id="civility-mr-cfs" />
                        <Label htmlFor="civility-mr-cfs">Monsieur</Label>
                      </div>
                      <div className="flex items-center space-x-2">
                        <RadioGroupItem value="mme" id="civility-mme-cfs" />
                        <Label htmlFor="civility-mme-cfs">Madame</Label>
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
                        className={`w-full rounded-lg border ${errors.firstName ? 'border-destructive' : 'border-input'} bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 ${errors.firstName ? 'focus:border-destructive focus:ring-destructive/20' : 'focus:border-primary focus:ring-primary/20'} transition-all`}
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
                        className={`w-full rounded-lg border ${errors.lastName ? 'border-destructive' : 'border-input'} bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 ${errors.lastName ? 'focus:border-destructive focus:ring-destructive/20' : 'focus:border-primary focus:ring-primary/20'} transition-all`}
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
                      onValueChange={(value) => setFormData((prev) => ({ ...prev, phone: value }))}
                      onCountryCodeChange={(code) => setFormData((prev) => ({ ...prev, countryCode: code }))}
                      onCountryIdChange={(id) => setFormData((prev) => ({ ...prev, id_pays_tel: id }))}
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
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ContactFormSimple;
