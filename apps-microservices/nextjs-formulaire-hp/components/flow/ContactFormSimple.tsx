'use client';

import { ArrowLeft, Send, Shield, Clock, CheckCircle } from "lucide-react";
import { useState, useMemo } from "react";
import CountryCodeSelect from "./CountryCodeSelect";
import ProgressHeader from "./ProgressHeader";

// Mock list of existing buyers in database
const EXISTING_BUYERS = [
  "jean.dupont@entreprise.fr",
  "marie.martin@societe.com",
  "contact@hellopro.fr",
  "acheteur@garage-martin.fr",
];

interface ContactFormSimpleProps {
  onBack: () => void;
}

const STEPS = [
  { id: 1, label: "Votre besoin" },
  { id: 2, label: "Précisions" },
  { id: 3, label: "Vos coordonnées" },
];

const ContactFormSimple = ({ onBack }: ContactFormSimpleProps) => {
  const [formData, setFormData] = useState({
    email: "",
    firstName: "",
    lastName: "",
    countryCode: "+33",
    phone: "",
    message: "",
  });

  // Check if email is from an existing buyer
  const isExistingBuyer = useMemo(() => {
    if (!formData.email || formData.email.length < 5) return false;
    return EXISTING_BUYERS.some(
      (email) => email.toLowerCase() === formData.email.toLowerCase()
    );
  }, [formData.email]);

  // Check if email is valid format
  const isEmailValid = useMemo(() => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(formData.email);
  }, [formData.email]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Handle form submission
    console.log("Form submitted:", formData);
  };

  // Show additional fields only if email is valid and not an existing buyer
  const showAdditionalFields = isEmailValid && !isExistingBuyer;

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
                    <div className="flex gap-2">
                      <CountryCodeSelect
                        value={formData.countryCode}
                        onChange={(value) => setFormData({ ...formData, countryCode: value })}
                      />
                      <input
                        type="tel"
                        id="phone"
                        name="phone"
                        required
                        value={formData.phone}
                        onChange={handleChange}
                        className="flex-1 rounded-lg border border-input bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
                        placeholder="6 12 34 56 78"
                      />
                    </div>
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
                className="w-full rounded-xl bg-accent py-4 text-lg font-semibold text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25 transition-all flex items-center justify-center gap-2"
              >
                <Send className="h-5 w-5" />
                Envoyer ma demande
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ContactFormSimple;
