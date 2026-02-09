"use client";

import { ArrowLeft, Send, Shield, Clock, CheckCircle, Paperclip, X } from "lucide-react";
import { useState, useMemo, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { useLeadSubmission } from "@/hooks/api/useLeadSubmission";
import { useBuyerCheck } from "@/hooks/api";
import { useFlowStore } from "@/lib/stores/flow-store";
import type { Supplier, ContactFormData } from "@/types";
import PhoneInput from "./PhoneInput";
import { validatePhoneNumber } from "@/lib/utils/phone-validation";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { toast } from "@/hooks/use-toast";

// Analytics imports
import { trackContactFormView, trackFormValidationErrors } from "@/lib/analytics";

interface ContactFormProps {
  selectedSuppliers: Supplier[];
  onBack: () => void;
}

const ContactForm = ({ selectedSuppliers, onBack }: ContactFormProps) => {
  const router = useRouter();
  const {
    categoryId,
    userAnswers,
    profileData,
    selectedSupplierIds,
    setContactData,
    files: filesStore, 
    setFilesStore,
    addFilesStore

  } = useFlowStore();
  

  const leadSubmission = useLeadSubmission({ suppliers: selectedSuppliers });

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

  const [errors, setErrors] = useState<Partial<Record<keyof ContactFormData, string>>>({});
  const [files, setFiles] = useState<File[]>([]);

  // Ref pour éviter les doubles appels en StrictMode
  const hasTrackedView = useRef(false);

  // Track form view on mount
  useEffect(() => {
    if (hasTrackedView.current) return;
    hasTrackedView.current = true;
    trackContactFormView(selectedSuppliers.length);
  }, [selectedSuppliers.length]);

  // Check if email is valid format
  const isEmailValid = useMemo(() => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(formData.email);
  }, [formData.email]);

  // Dynamic buyer check via API
  const { data: buyerCheckResult } = useBuyerCheck(
    {
      email     : formData.email,
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
        email    : formData.email,      // L'email déjà saisi
        isKnown  : true,
        firstName: info.prenom || "",
        lastName : info.nom || "",
        phone    : info.tel || "",
        civility: info.cv || "",
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

  // Show additional fields only if email is valid and not a known buyer
  const showAdditionalFields = isEmailValid && !isKnownBuyer;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files);
      setFiles(prev => [...prev, ...newFiles]);

      // 2. Mise à jour du store (pour la persistance/soumission)
      addFilesStore(newFiles);

      e.target.value = '';
    }
  };

  const removeFile = (index: number) => {
    const updatedFiles = files.filter((_, i) => i !== index);

    setFiles(updatedFiles);
    setFilesStore(updatedFiles);
  };

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

    // Validation téléphone avec le nouveau système
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!(isKnownBuyer && buyerCheckResult?.infoBuyer)) {
      const isValid = validateForm();
      if (!isValid) return;
    }

    const userKnownStatus = isKnownBuyer ? 'known' as const : 'unknown' as const;

    const finalData = { 
      ...formData, 
      files: filesStore // On s'assure que les fichiers du store sont inclus
    };

    finalData.files.forEach((file, index) => {
      console.log(`Fichier ${index}:`, {
        nom: file.name,
        taille: file.size,
        type: file.type
      });
    });

    setContactData(finalData);

    // Submit lead
    leadSubmission.mutate({
      contact: finalData,
      profile: profileData!,
      answers: userAnswers,
      selectedSupplierIds: selectedSupplierIds,
      submittedAt: new Date().toISOString(),
      userKnownStatus,
      categoryId: categoryId?.toString(),
    });
  };

  return (
    <div className="p-6 space-y-6">
      {/* Back button */}
      <button
        onClick={onBack}
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Modifier ma sélection
      </button>

      {/* Centered content container */}
      <div className="mx-auto max-w-xl space-y-6">
        {/* Title */}
        <div>
          <h2 className="text-2xl font-bold text-foreground">Vos coordonnées</h2>
          <p className="mt-1 text-muted-foreground">
            Recevez vos devis personnalisés sous 48h
          </p>
        </div>

        {/* Selected suppliers summary */}
        <div className="rounded-xl bg-secondary p-4">
          <p className="text-sm font-medium text-foreground mb-3">
            Votre demande sera envoyée à :
          </p>
          <div className="flex flex-wrap gap-2">
            {selectedSuppliers.map((supplier) => (
              <span
                key={supplier.id}
                className="inline-flex items-center rounded-full bg-card border border-border px-3 py-1 text-sm font-medium text-foreground"
              >
                {supplier.supplierName}
              </span>
            ))}
          </div>
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
              className={`w-full rounded-lg border ${errors.email ? 'border-destructive' : 'border-input'} bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all`}
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
            {errors.email && <p className="mt-1 text-sm text-destructive">{errors.email}</p>}
          </div>

          <div>
            <label
              htmlFor="message"
              className="block text-sm font-medium text-foreground mb-1.5"
            >
              Précisions pour les fournisseurs{" "}
              <span className="text-muted-foreground">(optionnel)</span>
            </label>
            <textarea
              id="message"
              name="message"
              rows={3}
              value={formData.message}
              onChange={handleChange}
              className="w-full rounded-lg border border-input bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all resize-none"
              placeholder="Délais souhaités, contraintes techniques..."
            />
          </div>

          {/* File upload */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1.5">
              Pièces jointes{" "}
              <span className="text-muted-foreground">(optionnel)</span>
            </label>

            {/* List of added files */}
            {files.length > 0 && (
              <div className="mb-2 space-y-2">
                {files.map((file, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between rounded-lg border border-input bg-secondary/50 px-3 py-2"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Paperclip className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="text-sm text-foreground truncate">{file.name}</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeFile(index)}
                      className="shrink-0 ml-2 p-1 rounded-full hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                      aria-label="Supprimer le fichier"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Add file button */}
            <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border-2 border-dashed border-input bg-background px-4 py-4 text-muted-foreground hover:border-primary/50 hover:bg-secondary/50 transition-all">
              <Paperclip className="h-5 w-5" />
              <span className="text-sm">
                {files.length > 0
                  ? "Ajouter un autre document"
                  : "Ajouter un document (cahier des charges, photo...)"}
              </span>
              <input
                type="file"
                className="hidden"
                onChange={handleFileChange}
                accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                multiple
              />
            </label>
          </div>

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
                <RadioGroupItem value="1" id="civility-mr-cf" />
                <Label htmlFor="civility-mr-cf">Monsieur</Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="2" id="civility-mme-cf" />
                <Label htmlFor="civility-mme-cf">Madame</Label>
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
                className={`w-full rounded-lg border ${errors.firstName ? 'border-destructive' : 'border-input'} bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all`}
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
                className={`w-full rounded-lg border ${errors.lastName ? 'border-destructive' : 'border-input'} bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all`}
              />
              {errors.lastName && <p className="mt-1 text-sm text-destructive">{errors.lastName}</p>}
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
              Ces fournisseurs s'engagent à vous répondre sous 48h
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Shield className="h-4 w-4 text-primary" />
              Vos coordonnées sont uniquement partagées avec les fournisseurs
              choisis
            </div>
          </div>

          {/* Submit button */}
          <button
            type="submit"
            disabled={leadSubmission.isPending}
            className="w-full rounded-xl bg-accent py-4 text-lg font-semibold text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25 transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {leadSubmission.isPending ? (
              <>
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent-foreground border-t-transparent" />
                Envoi en cours...
              </>
            ) : (
              <>
                <Send className="h-5 w-5" />
                Envoyer ma demande
              </>
            )}
          </button>

          {leadSubmission.isError && (
            <p className="text-center text-sm text-destructive">
              Une erreur est survenue. Veuillez réessayer.
            </p>
          )}
        </form>
      </div>
    </div>
  );
};

export default ContactForm;
