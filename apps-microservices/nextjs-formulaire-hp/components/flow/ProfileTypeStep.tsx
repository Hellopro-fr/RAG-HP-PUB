'use client';

import { useState, useMemo, useEffect, useRef } from "react";
import { ArrowLeft, ArrowRight, Search, Building2, Sparkles, Globe, User, MapPin, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import ProgressHeader from "./ProgressHeader";
import { useSirenSearch } from "@/hooks/api";
import { usePostalCodeSearch } from "@/hooks/usePostalCodeSearch";
import { useFlowStore } from "@/lib/stores/flow-store";
import type { ProfileType, CompanyResult, ProfileData } from "@/types";
import type { SirenCompanyData } from "@/lib/api/services/siret.service";
import {
  trackProfileView,
  trackProfileComplete,
} from "@/lib/analytics";


interface Country {
  id: number;
  libelle: string;
}

interface ProfileTypeStepProps {
  priorityCountries: Country[];
  otherCountries: Country[];
  onComplete: (data: ProfileData) => void;
  onBack: () => void;
}

const STEPS = [
  { id: 1, label: "Votre besoin" },
  { id: 2, label: "Sélection" },
  { id: 3, label: "Demande de devis" },
];

const ProfileTypeStep = ({ priorityCountries, otherCountries, onComplete, onBack }: ProfileTypeStepProps) => {
  // Store Zustand pour persistance dans sessionStorage
  const { setProfileData } = useFlowStore();

  // Ref pour éviter les doubles appels en StrictMode
  const hasTrackedView = useRef(false);

  // Track profile view au montage
  useEffect(() => {
    if (!hasTrackedView.current) {
      hasTrackedView.current = true;
      trackProfileView();
    }
  }, []);

  const [selectedType, setSelectedType] = useState<ProfileType>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCompany, setSelectedCompany] = useState<CompanyResult | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [city, setCity] = useState("");
  const [particulierCity, setParticulierCity] = useState("");
  const [country, setCountry] = useState("");
  const [countryID, setCountryID] = useState(0);
  const [showCountryDropdown, setShowCountryDropdown] = useState(false);
  const [countrySearch, setCountrySearch] = useState("");
  const [showPostalCodeSuggestions, setShowPostalCodeSuggestions] = useState(false);
  const [particulierShowPostalCodeSuggestions, setShowParticulierPostalCodeSuggestions] = useState(false);
  const [showManualCompanyForm, setShowManualCompanyForm] = useState(false);
  const [manualCompanyName, setManualCompanyName] = useState("");
  const [manualPostalCode, setManualPostalCode] = useState("");
  const [manualCity, setManualCity] = useState("");
  const [showManualPostalCodeSuggestions, setShowManualPostalCodeSuggestions] = useState(false);
  // Pour particulier - sélection du pays
  const [particulierCountry, setParticulierCountry] = useState("France");
  const [particulierCountryID, setParticulierCountryID] = useState(1);
  const [showParticulierCountryDropdown, setShowParticulierCountryDropdown] = useState(false);
  const [particulierCountrySearch, setParticulierCountrySearch] = useState("");
  const [particulierPostalCode, setParticulierPostalCode] = useState("");
  // Pour création - sélection du pays
  const [creationCountry, setCreationCountry] = useState("France");
  const [creationCountryID, setCreationCountryID] = useState(1);
  const [showCreationCountryDropdown, setShowCreationCountryDropdown] = useState(false);
  const [creationCountrySearch, setCreationCountrySearch] = useState("");


  // SIREN search via API
  const { data: sirenResults, isLoading: sirenLoading } = useSirenSearch(
    { query: searchQuery },
    searchQuery.length >= 2 && !selectedCompany && !showManualCompanyForm
  );

  // Postal code search for "creation" section
  const {
    data: postalCodeResults,
    isLoading: postalCodeLoading
  } = usePostalCodeSearch({
    query: postalCode,
    enabled: postalCode.length >= 3 && !city && selectedType === "creation",
  });

  // Postal code search for manual company form
  const {
    data: manualPostalCodeResults,
    isLoading: manualPostalCodeLoading
  } = usePostalCodeSearch({
    query: manualPostalCode,
    enabled: manualPostalCode.length >= 3 && !manualCity && showManualCompanyForm,
  });

  // Postal code search for particulier section
  const {
    data: particulierPostalCodeResults,
    isLoading: particulierPostalCodeLoading
  } = usePostalCodeSearch({
    query: particulierPostalCode,
    enabled: particulierCountry === "France" && particulierPostalCode.length >= 3 && !particulierCity && selectedType === "particulier",
  });



  // Liste des pays avec séparateur pour l'affichage
  const COUNTRIES_WITH_SEPARATOR = useMemo(() => {
    const priorityCountryIds = new Set(priorityCountries.map((c) => c.libelle));
    const filteredOtherCountries = otherCountries.filter(
      function(c){
        return !priorityCountryIds.has(c.libelle);
      }
    );
    return [...priorityCountries, "---" as const, ...filteredOtherCountries];
  }, [priorityCountries, otherCountries]);

  // Liste des pays sans séparateur (pour les filtres)
  const ALL_COUNTRIES = useMemo(() => {
    const priorityCountryIds = new Set(priorityCountries.map((c) => c.libelle));
    const filteredOtherCountries = otherCountries.filter((c) => !priorityCountryIds.has(c.libelle));
    return [...priorityCountries, ...filteredOtherCountries];
  }, [priorityCountries, otherCountries]);

  // Remplacer les suggestions de code postal par les résultats de l'API
  const postalCodeSuggestions = useMemo(() => {
    return postalCodeResults.slice(0, 8);
  }, [postalCodeResults]);

  const manualPostalCodeSuggestions = useMemo(() => {
    return manualPostalCodeResults.slice(0, 8);
  }, [manualPostalCodeResults]);

  const particulierPostalCodeSuggestions = useMemo(() => {
    return particulierPostalCodeResults.slice(0, 8);
  }, [particulierPostalCodeResults]);

  // Companies come from API (sirenResults)
  const filteredCompanies: SirenCompanyData[] = sirenResults || [];

  // Filter countries based on search
  const filteredCountries = useMemo(() => {
    if (!countrySearch.trim()) return COUNTRIES_WITH_SEPARATOR;
    return ALL_COUNTRIES.filter((c) =>
      c.libelle.toLowerCase().includes(countrySearch.toLowerCase())
    );
  }, [countrySearch, COUNTRIES_WITH_SEPARATOR, ALL_COUNTRIES]);

  // Filter countries based on search for particulier
  const filteredParticulierCountries = useMemo(() => {
    if (!particulierCountrySearch.trim()) return ALL_COUNTRIES;
    return ALL_COUNTRIES.filter((c) =>
      c.libelle.toLowerCase().includes(particulierCountrySearch.toLowerCase())
    );
  }, [particulierCountrySearch, ALL_COUNTRIES]);

  // Filter countries based on search for creation (excludes France)
  const filteredCreationCountries = useMemo(() => {
    const countriesExcludingFrance = ALL_COUNTRIES.filter((c) => c.libelle !== "France");
    if (!creationCountrySearch.trim()) return countriesExcludingFrance;
    return countriesExcludingFrance.filter((c) =>
      c.libelle.toLowerCase().includes(creationCountrySearch.toLowerCase())
    );
  }, [creationCountrySearch, ALL_COUNTRIES]);

  // Check if form is valid
  const isValid = useMemo(() => {
    switch (selectedType) {
      case "pro_france":
        if (showManualCompanyForm) {
          return manualCompanyName.trim().length > 0 && manualPostalCode.trim().length >= 5 && manualCity.trim().length > 0;
        }
        return selectedCompany !== null;
      case "creation":
        // Si France, require code postal et ville; sinon juste le pays
        if (creationCountryID === 1) {
          return postalCode.trim().length >= 5 && city.trim().length > 0;
        }
        return creationCountryID > 0;
      case "pro_foreign":
        return companyName.trim().length > 0 && country.trim().length > 0;
      case "particulier":
        // Si France, require code postal et ville; sinon juste le pays
        if (particulierCountryID == 1) {
          return particulierPostalCode.trim().length >= 5 && particulierCity.trim().length > 0;
        }
        return particulierCountryID > 0;
      default:
        return false;
    }
  }, [selectedType, selectedCompany, postalCode, city, companyName, countryID, showManualCompanyForm, manualCompanyName, manualPostalCode, manualCity, particulierCountryID, particulierPostalCode, particulierCity, creationCountryID]);

  const handleNext = () => {
    if (!isValid) return;

    const data: ProfileData = { type: selectedType };
    let info_datalayer = 'unkown';

    switch (selectedType) {
      case "pro_france":
        if (showManualCompanyForm) {
          data.countryID   = 1;
          data.companyName = manualCompanyName;
          data.postalCode  = manualPostalCode;
          data.city        = manualCity;

        } else {
          data.countryID   = 1;
          data.companyName = selectedCompany?.name;
          data.postalCode  = selectedCompany?.postalCode;
          data.city        = selectedCompany?.city;
          data.siren       = selectedCompany?.siren;
          data.siret       = selectedCompany?.siret;
          data.naf         = selectedCompany?.naf;
        }
        info_datalayer = 'pro_france';
        break;

      case "creation":
        data.country   = creationCountry;
        data.countryID = creationCountryID;
        if (creationCountryID === 1) {
          data.postalCode = postalCode;
          data.city       = city;
        }
        info_datalayer = 'creation_societe';
        break;

      case "particulier":
        data.country   = particulierCountry;
        data.countryID = particulierCountryID;
        if (particulierCountryID == 1) {
          data.postalCode = particulierPostalCode;
          data.city       = particulierCity;
        }
        info_datalayer = 'particulier';
        break;

      case "pro_foreign":
        data.companyName = companyName;
        data.country     = country;
        data.countryID   = countryID;
        info_datalayer = 'pro_etranger';
        break;
    }

    // Persister dans le store Zustand (sessionStorage)
    setProfileData(data);

    // Track profile complete
    trackProfileComplete(info_datalayer || 'unknown');

    onComplete(data);
  };

  const handleSelectCompany = (company: SirenCompanyData) => {
    // Convertir SirenCompanyData en CompanyResult
    const companyResult: CompanyResult = {
      siren: company.siren,
      name: company.name,
      address: company.address,
      postalCode: company.postalCode,
      city: company.city,
      naf: company.naf,
    };
    setSelectedCompany(companyResult);
    setSearchQuery(company.name);
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      <ProgressHeader
        steps={STEPS}
        currentStep={1}
        progress={90}
      />

      <div className="flex-1 overflow-y-auto">
        <div className="flex flex-col min-h-full">
          <div className="flex-1 p-4 sm:p-6 lg:p-10 pb-32 sm:pb-6">
            <div className="mx-auto max-w-2xl space-y-6 sm:space-y-8">
              {/* Title */}
              <div className="text-center space-y-4">
                <h2 className="text-lg sm:text-xl lg:text-2xl font-bold text-foreground leading-tight">
                  Êtes-vous un professionnel ou un particulier ?
                </h2>

                {/* Reassurance banner - connected to the question */}
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

              {/* Options */}
              <div className="space-y-3">
                {/* Option 1: Professional based in France */}
                <div
                  className={cn(
                    "rounded-xl border-2 p-4 transition-all",
                    selectedType === "pro_france"
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  )}
                >
                  <button
                    onClick={() => {
                      setSelectedType("pro_france");
                      setSelectedCompany(null);
                      setSearchQuery("");
                      setShowManualCompanyForm(false);
                      setManualCompanyName("");
                      setManualPostalCode("");
                      setManualCity("");
                    }}
                    className="w-full text-left"
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className={cn(
                          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors mt-0.5",
                          selectedType === "pro_france"
                            ? "border-primary bg-primary"
                            : "border-muted-foreground/30"
                        )}
                      >
                        {selectedType === "pro_france" && (
                          <div className="h-2 w-2 rounded-full bg-primary-foreground" />
                        )}
                      </div>
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <Building2 className="h-5 w-5 text-primary shrink-0" />
                          <span className="font-medium text-primary">Professionnel basé en France</span>
                        </div>
                        <span className="text-sm text-muted-foreground">(entreprises, associations, collectivités...)</span>
                      </div>
                    </div>
                  </button>

                  {selectedType === "pro_france" && (
                    <div className="mt-4 space-y-3">
                      <label className="text-sm text-muted-foreground">
                        Saisissez le nom de votre structure ou le SIREN
                      </label>
                      <div className="relative">
                        <div className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2.5 focus-within:border-primary focus-within:ring-1 focus-within:ring-primary">
                          <Search className="h-4 w-4 text-muted-foreground" />
                          <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => {
                              setSearchQuery(e.target.value);
                              setSelectedCompany(null);
                            }}
                            placeholder="Ex: Orange, 832435325"
                            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                          />
                        </div>
                      </div>

                      {/* Company suggestions */}
                      {searchQuery.length >= 2 && !selectedCompany && !showManualCompanyForm && (
                        <div className="space-y-2">
                          <p className="text-sm text-center text-muted-foreground">
                            Sélectionnez votre structure si elle s'affiche :
                          </p>
                          <button
                            onClick={() => setShowManualCompanyForm(true)}
                            className="mx-auto block rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
                          >
                            Ma structure n'est pas dans la liste
                          </button>

                          {sirenLoading ? (
                            <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
                              <Loader2 className="h-4 w-4 animate-spin" />
                              Recherche en cours...
                            </div>
                          ) : (
                            <div className="max-h-64 overflow-y-auto rounded-lg border border-border bg-card shadow-lg">
                              {filteredCompanies.length > 0 ? (
                                filteredCompanies.map((company, index) => (
                                  <button
                                    key={`${company.siren}-${index}`}
                                    onClick={() => handleSelectCompany(company)}
                                    className={cn(
                                      "w-full text-left px-4 py-3 hover:bg-muted transition-colors",
                                      index !== filteredCompanies.length - 1 && "border-b border-border"
                                    )}
                                  >
                                    <div className="font-medium text-foreground">{company.name}</div>
                                    <div className="text-sm text-muted-foreground">
                                      SIREN : {company.siren} &nbsp;&nbsp; {company.address}, {company.postalCode} {company.city}
                                    </div>
                                  </button>
                                ))
                              ) : (
                                <div className="px-4 py-3 text-sm text-muted-foreground text-center bg-card">
                                  Aucune entreprise trouvée
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Manual company form */}
                      {showManualCompanyForm && (
                        <div className="space-y-4 p-4 rounded-lg border border-border bg-muted/30">
                          <div className="flex items-center justify-between">
                            <p className="text-sm font-medium text-foreground">Renseignez votre structure</p>
                            <button
                              onClick={() => {
                                setShowManualCompanyForm(false);
                                setManualCompanyName("");
                                setManualPostalCode("");
                                setManualCity("");
                              }}
                              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                            >
                              ← Retour à la recherche
                            </button>
                          </div>

                          <div className="space-y-3">
                            <div>
                              <label className="text-sm text-muted-foreground">Nom de la société</label>
                              <input
                                type="text"
                                value={manualCompanyName}
                                onChange={(e) => setManualCompanyName(e.target.value)}
                                placeholder="Ex: Ma Société SARL"
                                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                              />
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                              <div className="relative">
                                <label className="text-sm text-muted-foreground">Code postal</label>
                                <input
                                  type="text"
                                  value={manualPostalCode}
                                  onChange={(e) => {
                                    const newPostalCode = e.target.value.replace(/\D/g, "").slice(0, 5);
                                    setManualPostalCode(newPostalCode);
                                    setManualCity("");
                                    setShowManualPostalCodeSuggestions(newPostalCode.length >= 1);
                                  }}
                                  onFocus={() => manualPostalCode.length >= 2 && setShowManualPostalCodeSuggestions(true)}
                                  onBlur={() => {setTimeout(() => setShowManualPostalCodeSuggestions(false), 200);}}
                                  placeholder="75001"
                                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                                />

                                {showManualPostalCodeSuggestions && manualPostalCodeSuggestions.length > 0 && !manualCity && (
                                  <div className="absolute z-50 mt-1 w-[calc(200%+0.75rem)] rounded-lg border border-border bg-card shadow-lg max-h-48 overflow-y-auto">
                                    {manualPostalCodeLoading ? (
                                      <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                        Recherche...
                                      </div>
                                    ) : manualPostalCodeSuggestions.length > 0 ? (
                                      manualPostalCodeSuggestions.map((item, index) => (
                                        <button
                                          key={`manual-${item.postalCode}-${item.city}-${index}`}
                                          onClick={() => {
                                            setManualPostalCode(item.postalCode);
                                            setManualCity(item.city);
                                            setShowManualPostalCodeSuggestions(false);
                                          }}
                                          className={cn(
                                            "w-full text-left px-3 py-2 hover:bg-muted transition-colors text-sm",
                                            index !== manualPostalCodeSuggestions.length - 1 && "border-b border-border"
                                          )}
                                        >
                                          <span className="font-medium text-foreground">{item.postalCode}</span>
                                          <span className="text-muted-foreground"> - {item.city}</span>
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

                              <div>
                                <label className="text-sm text-muted-foreground">Ville</label>
                                <input
                                  type="text"
                                  value={manualCity}
                                  onChange={(e) => setManualCity(e.target.value)}
                                  placeholder="Paris"
                                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                                />
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      {selectedCompany && (
                        <div className="rounded-lg border border-primary/30 bg-primary/5 px-4 py-3">
                          <div className="font-medium text-foreground">{selectedCompany.name}</div>
                          <div className="text-sm text-muted-foreground">
                            SIREN : {selectedCompany.siren} &nbsp;&nbsp; {selectedCompany.address}, {selectedCompany.postalCode} {selectedCompany.city}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Option 2: Company being created */}
                <div
                  className={cn(
                    "rounded-xl border-2 p-4 transition-all",
                    selectedType === "creation"
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  )}
                >
                  <button
                    onClick={() => {
                      setSelectedType("creation");
                    }}
                    className="w-full text-left"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors",
                          selectedType === "creation"
                            ? "border-primary bg-primary"
                            : "border-muted-foreground/30"
                        )}
                      >
                        {selectedType === "creation" && (
                          <div className="h-2 w-2 rounded-full bg-primary-foreground" />
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Sparkles className="h-5 w-5 text-muted-foreground shrink-0" />
                        <span className="font-medium text-foreground">Société en cours de création</span>
                      </div>
                    </div>
                  </button>

                  {selectedType === "creation" && (
                    <div className="mt-4 ml-8 space-y-3">
                      <p className="text-sm text-muted-foreground">Merci de renseigner votre localisation</p>

                      {/* Country selection for creation */}
                      <div className="relative">
                        <label className="text-sm text-muted-foreground">Pays</label>
                        <button
                          type="button"
                          onClick={() => setShowCreationCountryDropdown(!showCreationCountryDropdown)}
                          className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground text-left focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary flex items-center justify-between"
                        >
                          <span>{creationCountry || "Sélectionner un pays"}</span>
                          <Globe className="h-4 w-4 text-muted-foreground" />
                        </button>

                        {showCreationCountryDropdown && (
                          <div className="absolute z-50 mt-1 w-full rounded-lg border border-border bg-card shadow-lg max-h-64 overflow-hidden">
                            <div className="p-2 border-b border-border">
                              <div className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
                                <Search className="h-4 w-4 text-muted-foreground" />
                                <input
                                  type="text"
                                  value={creationCountrySearch}
                                  onChange={(e) => setCreationCountrySearch(e.target.value)}
                                  placeholder="Rechercher un pays..."
                                  className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                                  autoFocus
                                />
                              </div>
                            </div>
                            <div className="max-h-48 overflow-y-auto">
                              {/* France always first */}
                              <button
                                onClick={() => {
                                  setCreationCountry("France");
                                  setCreationCountryID(1);
                                  setShowCreationCountryDropdown(false);
                                  setCreationCountrySearch("");
                                }}
                                className={cn(
                                  "w-full text-left px-4 py-2.5 text-sm hover:bg-muted transition-colors border-b border-border",
                                  creationCountryID === 1 && "bg-primary/10 text-primary font-medium"
                                )}
                              >
                                France
                              </button>
                              {filteredCreationCountries.map((countryItem) => (
                                  <button
                                    key={countryItem.id}
                                    onClick={() => {
                                      setCreationCountry(countryItem.libelle);
                                      setCreationCountryID(countryItem.id);
                                      setShowCreationCountryDropdown(false);
                                      setCreationCountrySearch("");
                                      // Reset postal code and city when country changes
                                      setPostalCode("");
                                      setCity("");
                                    }}
                                    className={cn(
                                      "w-full text-left px-4 py-2.5 text-sm hover:bg-muted transition-colors",
                                      creationCountryID === countryItem.id && "bg-primary/10 text-primary font-medium"
                                    )}
                                  >
                                    {countryItem.libelle}
                                  </button>
                                ))}
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Postal code and city only for France */}
                      {creationCountryID === 1 && (
                        <div className="grid grid-cols-2 gap-3">
                          <div className="relative">
                            <label className="text-sm text-muted-foreground">Code postal</label>
                            <input
                              type="text"
                              value={postalCode}
                              onChange={(e) => {
                                const newPostalCode = e.target.value.replace(/\D/g, "").slice(0, 5);
                                setPostalCode(newPostalCode);
                                setCity("");
                                setShowPostalCodeSuggestions(newPostalCode.length >= 1);
                              console.log("New postal code:", showPostalCodeSuggestions);
                              }}
                              onFocus={() => postalCode.length >= 2 && setShowPostalCodeSuggestions(true)}
                              onBlur={() => {setTimeout(() => setShowPostalCodeSuggestions(false), 200);}}
                              placeholder="75001"
                              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                            />

                            {showPostalCodeSuggestions && postalCode.length >= 1 && !city && (
                              <div className="absolute z-50 mt-1 w-[calc(200%+0.75rem)] rounded-lg border border-border bg-card shadow-lg max-h-48 overflow-y-auto">
                                {postalCodeLoading ? (
                                  <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    Recherche...
                                  </div>
                                ) : postalCodeSuggestions.length > 0 ? (
                                  postalCodeSuggestions.map((item, index) => (
                                    <button
                                      key={`creation-${item.postalCode}-${item.city}-${index}`}
                                      onClick={() => {
                                        setPostalCode(item.postalCode);
                                        setCity(item.city);
                                        setShowPostalCodeSuggestions(false);
                                      }}
                                      className={cn(
                                        "w-full text-left px-4 py-2.5 text-sm hover:bg-muted transition-colors",
                                        index === 0 && "rounded-t-lg",
                                        index === postalCodeSuggestions.length - 1 && "rounded-b-lg"
                                      )}
                                    >
                                      <span className="font-medium">{item.postalCode}</span>
                                      <span className="text-muted-foreground"> — {item.city}</span>
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
                          <div>
                            <label className="text-sm text-muted-foreground">Ville</label>
                            <input
                              type="text"
                              value={city}
                              onChange={(e) => setCity(e.target.value)}
                              placeholder="Ville"
                              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Option 3: Professional outside France */}
                <div
                  className={cn(
                    "rounded-xl border-2 p-4 transition-all",
                    selectedType === "pro_foreign"
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  )}
                >
                  <button
                    onClick={() => {
                      setSelectedType("pro_foreign");
                    }}
                    className="w-full text-left"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors",
                          selectedType === "pro_foreign"
                            ? "border-primary bg-primary"
                            : "border-muted-foreground/30"
                        )}
                      >
                        {selectedType === "pro_foreign" && (
                          <div className="h-2 w-2 rounded-full bg-primary-foreground" />
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Globe className="h-5 w-5 text-muted-foreground shrink-0" />
                        <span className="font-medium text-foreground">Professionnel hors de France</span>
                      </div>
                    </div>
                  </button>

                  {selectedType === "pro_foreign" && (
                    <div className="mt-4 ml-8 space-y-3">
                      <p className="text-sm text-muted-foreground">Merci de renseigner vos informations</p>
                      <div className="space-y-3">
                        <div>
                          <label className="text-sm text-muted-foreground">Votre structure</label>
                          <input
                            type="text"
                            value={companyName}
                            onChange={(e) => setCompanyName(e.target.value)}
                            placeholder="Nom de votre société / association / collectivité..."
                            className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                          />
                        </div>
                        <div className="relative">
                          <label className="text-sm text-muted-foreground">Pays</label>
                          <button
                            onClick={() => setShowCountryDropdown(!showCountryDropdown)}
                            className="mt-1 w-full flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-left focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                          >
                            <span className={country ? "text-foreground" : "text-muted-foreground"}>
                              {country || "Sélectionner un pays"}
                            </span>
                            <Globe className="h-4 w-4 text-muted-foreground" />
                          </button>

                          {showCountryDropdown && (
                            <div className="absolute z-10 mt-1 w-full rounded-lg border border-border bg-background shadow-lg">
                              <div className="p-2 border-b border-border">
                                <input
                                  type="text"
                                  value={countrySearch}
                                  onChange={(e) => setCountrySearch(e.target.value)}
                                  placeholder="Rechercher..."
                                  className="w-full rounded-md border border-border bg-muted/30 px-3 py-2 text-sm focus:outline-none focus:border-primary"
                                  autoFocus
                                />
                              </div>
                              <div className="max-h-48 overflow-y-auto">
                                {filteredCountries.map((c) => {
                                  // Séparateur entre pays prioritaires et autres pays
                                  if (c === "---") {
                                    return (
                                      <div
                                        key={c}
                                        className="border-t border-border my-1"
                                        aria-hidden="true"
                                      />
                                    );
                                  }

                                  if(c.id !== 1){
                                    return (
                                      <button
                                        key={c.id}
                                        onClick={() => {
                                          setCountry(c.libelle);
                                          setCountryID(c.id);
                                          setShowCountryDropdown(false);
                                          setCountrySearch("");
                                        }}
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-muted/50 transition-colors"
                                      >
                                        {c.libelle}
                                      </button>
                                    );
                                  }

                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Option 4: Individual */}
                <div
                  className={cn(
                    "rounded-xl border-2 p-4 transition-all",
                    selectedType === "particulier"
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  )}
                >
                  <button
                    onClick={() => {
                      setSelectedType("particulier");
                    }}
                    className="w-full text-left"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors",
                          selectedType === "particulier"
                            ? "border-primary bg-primary"
                            : "border-muted-foreground/30"
                        )}
                      >
                        {selectedType === "particulier" && (
                          <div className="h-2 w-2 rounded-full bg-primary-foreground" />
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <User className="h-5 w-5 text-muted-foreground shrink-0" />
                        <span className="font-medium text-foreground">Particulier</span>
                      </div>
                    </div>
                  </button>

                  {selectedType === "particulier" && (
                    <div className="mt-4 ml-8 space-y-3">
                      <p className="text-sm text-muted-foreground">Merci de renseigner votre localisation</p>

                      {/* Country selector */}
                      <div className="relative">
                        <label className="text-sm text-muted-foreground">Pays</label>
                        <button
                          onClick={() => setShowParticulierCountryDropdown(!showParticulierCountryDropdown)}
                          className="mt-1 w-full flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-left focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                        >
                          <span className="text-foreground">{particulierCountry}</span>
                          <Globe className="h-4 w-4 text-muted-foreground" />
                        </button>

                        {showParticulierCountryDropdown && (
                          <div className="absolute z-50 mt-1 w-full rounded-lg border border-border bg-background shadow-lg">
                            <div className="p-2 border-b border-border">
                              <input
                                type="text"
                                value={particulierCountrySearch}
                                onChange={(e) => setParticulierCountrySearch(e.target.value)}
                                placeholder="Rechercher..."
                                className="w-full rounded-md border border-border bg-muted/30 px-3 py-2 text-sm focus:outline-none focus:border-primary"
                                autoFocus
                              />
                            </div>
                            <div className="max-h-48 overflow-y-auto">
                              {/* France always first */}
                              <button
                                onClick={() => {
                                  setParticulierCountry("France");
                                  setShowParticulierCountryDropdown(false);
                                  setParticulierCountrySearch("");
                                }}
                                className={cn(
                                  "w-full text-left px-4 py-2 text-sm hover:bg-muted/50 transition-colors",
                                  particulierCountry === "France" && "bg-primary/10 font-medium"
                                )}
                              >
                                France
                              </button>
                              {filteredParticulierCountries.filter(c => c.libelle !== "France").map((c) => (
                                <button
                                  key={c.id}
                                  onClick={() => {
                                    setParticulierCountry(c.libelle);
                                    setShowParticulierCountryDropdown(false);
                                    setParticulierCountryID(c.id);
                                    setParticulierCountrySearch("");
                                    // Clear postal code and city when changing country
                                    setParticulierPostalCode("");
                                    setParticulierCity("");
                                  }}
                                  className="w-full text-left px-4 py-2 text-sm hover:bg-muted/50 transition-colors"
                                >
                                  {c.libelle}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Postal code and city - only shown if France */}
                      {particulierCountry === "France" && (
                        <div className="grid grid-cols-2 gap-3">
                          <div className="relative">
                            <label className="text-sm text-muted-foreground">Code postal</label>
                            <input
                              type="text"
                              value={particulierPostalCode}
                              onChange={(e) => {
                                const newPostalCode = e.target.value.replace(/\D/g, "").slice(0, 5);
                                setParticulierPostalCode(newPostalCode);
                                setParticulierCity("");
                                setShowParticulierPostalCodeSuggestions(true);
                              }}
                              onFocus={() => particulierPostalCode.length >= 2 && setShowParticulierPostalCodeSuggestions(true)}
                              onBlur={() => {setTimeout(() => setShowParticulierPostalCodeSuggestions(false), 200);}}
                              placeholder="75001"
                              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                            />

                            {particulierShowPostalCodeSuggestions && particulierPostalCode.length >=1 && (
                              <div className="absolute z-50 mt-1 w-[calc(200%+0.75rem)] rounded-lg border border-border bg-card shadow-lg max-h-48 overflow-y-auto">
                                {particulierPostalCodeLoading ? (
                                  <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    Recherche...
                                  </div>
                                ) : particulierPostalCodeSuggestions.length > 0 ? (
                                  particulierPostalCodeSuggestions.map((item, index) => (
                                    <button
                                      key={`particulier-${item.postalCode}-${item.city}-${index}`}
                                      onClick={() => {
                                        setParticulierPostalCode(item.postalCode);
                                        setParticulierCity(item.city);
                                        setShowParticulierPostalCodeSuggestions(false);
                                      }}
                                      className={cn(
                                        "w-full text-left px-4 py-2.5 text-sm hover:bg-muted transition-colors",
                                        index === 0 && "rounded-t-lg",
                                        index === particulierPostalCodeSuggestions.length - 1 && "rounded-b-lg"
                                      )}
                                    >
                                      <span className="font-medium">{item.postalCode}</span>
                                      <span className="text-muted-foreground"> — {item.city}</span>
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
                          <div>
                            <label className="text-sm text-muted-foreground">Ville</label>
                            <input
                              type="text"
                              value={particulierCity}
                              onChange={(e) => setParticulierCity(e.target.value)}
                              placeholder="Ville"
                              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Desktop navigation */}
              <div className="hidden sm:flex items-center justify-between pt-4">
                <button
                  onClick={onBack}
                  className="flex items-center gap-2 rounded-lg border-2 border-border bg-background px-5 py-3 text-sm font-medium transition-colors hover:bg-muted text-foreground"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Retour
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
            </div>
          </div>

          {/* Mobile sticky footer */}
          <div className="sm:hidden fixed bottom-0 left-0 right-0 bg-background border-t border-border p-4 shadow-[0_-4px_20px_rgba(0,0,0,0.1)]">
            <div className="flex items-center gap-3">
              <button
                onClick={onBack}
                className="flex items-center justify-center rounded-lg border-2 border-border bg-background px-4 py-3 text-sm font-medium transition-colors hover:bg-muted text-foreground"
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
  );
};

export default ProfileTypeStep;
