'use client';

import { useState, useMemo } from "react";
import { ArrowLeft, ArrowRight, MapPin, Globe, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import ProgressHeader from "./ProgressHeader";
import { usePostalCodeSearch } from "@/hooks/usePostalCodeSearch";


interface Country {
  id: number;
  libelle: string;
}


const STEPS = [
  { id: 1, label: "Votre besoin" },
  { id: 2, label: "Sélection" },
  { id: 3, label: "Demande de devis" },
];

export interface GeoData {
  countryId: number;
  country: string;
  postalCode: string;
  city: string;
}

interface GeoZoneStepProps {
  priorityCountries: Country[];
  otherCountries: Country[];
  onComplete: (data: GeoData) => void | Promise<void>;
  onBack: () => void;
}

const GeoZoneStep = ({ priorityCountries = [], otherCountries = [], onComplete, onBack }: GeoZoneStepProps) => {
  const [country, setCountry] = useState("France");
  const [countryId, setCountryId] = useState(1);
  const [postalCode, setPostalCode] = useState("");
  const [city, setCity] = useState("");
  const [showPostalCodeSuggestions, setShowPostalCodeSuggestions] = useState(false);
  const [showCountryDropdown, setShowCountryDropdown] = useState(false);
  const [countrySearch, setCountrySearch] = useState("");

  // Liste des pays avec séparateur pour l'affichage
  const COUNTRIES_WITH_SEPARATOR = useMemo(() => {
    const priorityCountryNames = new Set((priorityCountries || []).map((c) => c.libelle));
    const filteredOtherCountries = (otherCountries || []).filter((c) => !priorityCountryNames.has(c.libelle));
    return [...(priorityCountries || []), "---" as const, ...filteredOtherCountries];
  }, [priorityCountries, otherCountries]);

  // Liste des pays sans séparateur (pour les filtres)
  const ALL_COUNTRIES = useMemo(() => {
    const priorityCountryNames = new Set((priorityCountries || []).map((c) => c.libelle));
    const filteredOtherCountries = (otherCountries || []).filter((c) => !priorityCountryNames.has(c.libelle));
    return [...(priorityCountries || []), ...filteredOtherCountries];
  }, [priorityCountries, otherCountries]);

  const filteredCountries = useMemo(() => {
    if (!countrySearch.trim()) return COUNTRIES_WITH_SEPARATOR;
    return ALL_COUNTRIES.filter((c) =>
      c.libelle.toLowerCase().includes(countrySearch.toLowerCase())
    );
  }, [countrySearch, COUNTRIES_WITH_SEPARATOR, ALL_COUNTRIES]);

  const isFrance = country === "France";

  const { data: results, isLoading: postalCodeLoading } = usePostalCodeSearch({
    query: postalCode,
    enabled: postalCode.length >= 2 && !city && isFrance
  });

  const postalCodeSuggestions = useMemo(() => {
    return (results || []).slice(0, 8);
  }, [results]);

  const isValid = useMemo(() => {
    if (!country.trim()) return false;
    if (isFrance) return postalCode.trim().length >= 5 && city.trim().length > 0;
    return true;
  }, [country, postalCode, city, isFrance]);

  const handleNext = () => {
    if (!isValid) return;
    onComplete({ countryId, country, postalCode: isFrance ? postalCode : "", city: isFrance ? city : "" });
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      <ProgressHeader
        steps={STEPS}
        currentStep={1}
        progress={80}
      />

      <div className="flex-1 overflow-y-auto">
        <div className="flex flex-col min-h-full">
          <div className="flex-1 p-4 sm:p-6 lg:p-10 pb-32 sm:pb-6">
            <div className="mx-auto max-w-2xl space-y-6 sm:space-y-8">
              {/* Title */}
              <div className="text-center space-y-4">
                <h2 className="text-lg sm:text-xl lg:text-2xl font-bold text-foreground leading-tight">
                  Où êtes-vous situé ?
                </h2>

                <div className="inline-flex items-center gap-3 rounded-full bg-accent/15 border border-accent/30 px-5 py-2.5 shadow-sm">
                  <div className="flex items-center justify-center h-8 w-8 rounded-full bg-accent text-accent-foreground shrink-0">
                    <MapPin className="h-4 w-4" />
                  </div>
                  <span className="text-sm sm:text-base text-foreground">
                    <span className="font-semibold">Pourquoi cette info ?</span>
                    {" "}Pour vous proposer uniquement les fournisseurs qui livrent et installent <span className="font-semibold text-accent">près de chez vous</span>
                  </span>
                </div>
              </div>

              {/* Country selector */}
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Pays *</label>
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setShowCountryDropdown(!showCountryDropdown)}
                      className="w-full flex items-center justify-between rounded-lg border border-input bg-background px-4 py-3 text-foreground hover:border-primary/50 transition-colors"
                    >
                      <span>{country || "Sélectionnez un pays"}</span>
                      <Globe className="h-4 w-4 text-muted-foreground" />
                    </button>

                    {showCountryDropdown && (
                      <div className="absolute z-20 mt-1 w-full rounded-lg border border-border bg-card shadow-lg max-h-60 overflow-hidden">
                        <div className="p-2 border-b border-border">
                          <input
                            type="text"
                            value={countrySearch}
                            onChange={(e) => setCountrySearch(e.target.value)}
                            placeholder="Rechercher un pays..."
                            className="w-full bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                            autoFocus
                          />
                        </div>
                        <div className="overflow-y-auto max-h-48">
                          {/* France always first if no search */}
                          {!countrySearch && (
                            <button
                              type="button"
                              onClick={() => {
                                setCountryId(1);
                                setCountry("France");
                                setShowCountryDropdown(false);
                                setCountrySearch("");
                                // Reset postal code and city when country changes handled by useEffect or manually
                              }}
                              className={cn(
                                "w-full text-left px-4 py-2 text-sm hover:bg-muted transition-colors border-b border-border",
                                country === "France" ? "bg-primary/10 text-primary font-medium" : "text-foreground"
                              )}
                            >
                              France
                            </button>
                          )}
                          {filteredCountries.map((c, idx) => {
                            if (c === "---") {
                              return <div key="sep" className="h-px bg-border my-1" />;
                            }
                            const countryItem = c as Country;
                            return (
                              <button
                                key={countryItem.id}
                                type="button"
                                onClick={() => {
                                  setCountryId(countryItem.id);
                                  setCountry(countryItem.libelle);
                                  setShowCountryDropdown(false);
                                  setCountrySearch("");
                                  if (countryItem.libelle !== "France") { 
                                    setPostalCode(""); 
                                    setCity(""); 
                                  }
                                }}
                                className={cn(
                                  "w-full text-left px-4 py-2 text-sm hover:bg-muted transition-colors",
                                  countryItem.libelle === country ? "bg-primary/10 text-primary font-medium" : "text-foreground"
                                )}
                              >
                                {countryItem.libelle}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Postal code + City side by side - only if France */}
                {isFrance && (
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-foreground">Code postal *</label>
                      <div className="relative">
                        <input
                          type="text"
                          value={postalCode}
                          onChange={(e) => {
                            const val = e.target.value.replace(/\D/g, "").slice(0, 5);
                            setPostalCode(val);
                            setCity("");
                            setShowPostalCodeSuggestions(true);
                          }}
                          onFocus={() => setShowPostalCodeSuggestions(true)}
                          onBlur={() => setTimeout(() => setShowPostalCodeSuggestions(false), 200)}
                          placeholder="Ex: 75011"
                          className="w-full rounded-lg border border-input bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
                          maxLength={5}
                        />
                        {showPostalCodeSuggestions && postalCode.length >= 2 && !city && (
                          <div className="absolute z-20 mt-1 w-full rounded-lg border border-border bg-card shadow-lg max-h-48 overflow-y-auto">
                            {postalCodeLoading ? (
                              <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                                <Loader2 className="h-4 w-4 animate-spin" />
                                Recherche...
                              </div>
                            ) : postalCodeSuggestions.length > 0 ? (
                              postalCodeSuggestions.map((item, idx) => (
                                <button
                                  key={idx}
                                  type="button"
                                  onMouseDown={(e) => e.preventDefault()}
                                  onClick={() => {
                                    setPostalCode(item.postalCode);
                                    setCity(item.city);
                                    setShowPostalCodeSuggestions(false);
                                  }}
                                  className="w-full text-left px-4 py-2 text-sm hover:bg-muted transition-colors text-foreground"
                                >
                                  <span className="font-medium">{item.postalCode}</span> — {item.city}
                                </button>
                              ))
                            ) : (
                              <div className="px-4 py-3 text-sm text-muted-foreground text-center">
                                Aucune ville trouvée
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <label className="text-sm font-medium text-foreground">Ville *</label>
                      <input
                        type="text"
                        value={city}
                        onChange={(e) => setCity(e.target.value)}
                        placeholder="Ex: Paris 11e"
                        className="w-full rounded-lg border border-input bg-background px-4 py-3 text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="hidden sm:flex items-center justify-between pt-4">
                <button
                  onClick={onBack}
                  className="flex items-center gap-2 rounded-lg border-2 border-border bg-background px-5 py-3 text-sm font-medium text-foreground hover:bg-muted transition-colors"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Précédent
                </button>
                <button
                  onClick={handleNext}
                  disabled={!isValid}
                  className={cn(
                    "flex items-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold transition-all",
                    isValid
                      ? "bg-accent text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25"
                      : "bg-muted text-muted-foreground cursor-not-allowed"
                  )}
                >
                  Suivant
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>

              {/* Mobile sticky footer */}
              <div className="sm:hidden fixed bottom-0 left-0 right-0 bg-background border-t border-border shadow-[0_-4px_20px_rgba(0,0,0,0.1)]">
                <div className="flex items-center gap-3 p-4">
                  <button
                    onClick={onBack}
                    className="flex items-center justify-center rounded-lg border-2 border-border bg-background px-4 py-3 text-sm font-medium hover:bg-muted text-foreground transition-colors"
                  >
                    <ArrowLeft className="h-5 w-5" />
                  </button>
                  <button
                    onClick={handleNext}
                    disabled={!isValid}
                    className={cn(
                      "flex-1 flex items-center justify-center gap-2 rounded-lg px-6 py-3.5 text-base font-semibold transition-all",
                      isValid
                        ? "bg-accent text-accent-foreground shadow-lg shadow-accent/25"
                        : "bg-muted text-muted-foreground cursor-not-allowed"
                    )}
                  >
                    Suivant
                    <ArrowRight className="h-5 w-5" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default GeoZoneStep;
