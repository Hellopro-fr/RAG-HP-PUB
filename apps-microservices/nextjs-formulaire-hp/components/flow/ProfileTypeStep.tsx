'use client';

import { useState, useMemo, useEffect, useRef } from "react";
import { ArrowLeft, ArrowRight, Search, Building2, Sparkles, Globe, User, MapPin, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import ProgressHeader from "./ProgressHeader";
import { CountrySelector, PostalCodeCityInput } from "./inputs";
import { useSirenSearch } from "@/hooks/api";
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

  // ===== ÉTAT PRINCIPAL =====
  const [selectedType, setSelectedType] = useState<ProfileType>(null);

  // ===== PRO FRANCE =====
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCompany, setSelectedCompany] = useState<CompanyResult | null>(null);
  const [showManualCompanyForm, setShowManualCompanyForm] = useState(false);
  const [manualCompanyName, setManualCompanyName] = useState("");
  const [manualPostalCode, setManualPostalCode] = useState("");
  const [manualCity, setManualCity] = useState("");

  // ===== CRÉATION =====
  const [creationCountry, setCreationCountry] = useState("France");
  const [creationCountryID, setCreationCountryID] = useState(1);
  const [creationPostalCode, setCreationPostalCode] = useState("");
  const [creationCity, setCreationCity] = useState("");

  // ===== PRO ÉTRANGER =====
  const [foreignCompanyName, setForeignCompanyName] = useState("");
  const [foreignCountry, setForeignCountry] = useState("");
  const [foreignCountryID, setForeignCountryID] = useState(0);

  // ===== PARTICULIER =====
  const [particulierCountry, setParticulierCountry] = useState("France");
  const [particulierCountryID, setParticulierCountryID] = useState(1);
  const [particulierPostalCode, setParticulierPostalCode] = useState("");
  const [particulierCity, setParticulierCity] = useState("");

  // ===== API HOOKS =====
  // SIREN search via API
  const { data: sirenResults, isLoading: sirenLoading } = useSirenSearch(
    { query: searchQuery },
    searchQuery.length >= 2 && !selectedCompany && !showManualCompanyForm
  );

  // Liste des pays combinée
  const allCountries = useMemo(() => {
    const priorityIds = new Set(priorityCountries.map((c) => c.libelle));
    const filteredOther = otherCountries.filter((c) => !priorityIds.has(c.libelle));
    return [...priorityCountries, ...filteredOther];
  }, [priorityCountries, otherCountries]);

  // Companies from API
  const filteredCompanies: SirenCompanyData[] = sirenResults || [];

  // ===== VALIDATION =====
  const isValid = useMemo(() => {
    switch (selectedType) {
      case "pro_france":
        if (showManualCompanyForm) {
          return manualCompanyName.trim().length > 0 && manualPostalCode.trim().length >= 5 && manualCity.trim().length > 0;
        }
        return selectedCompany !== null;
      case "creation":
        if (creationCountryID === 1) {
          return creationPostalCode.trim().length >= 5 && creationCity.trim().length > 0;
        }
        return creationCountryID > 0;
      case "pro_foreign":
        return foreignCompanyName.trim().length > 0 && foreignCountry.trim().length > 0;
      case "particulier":
        if (particulierCountryID === 1) {
          return particulierPostalCode.trim().length >= 5 && particulierCity.trim().length > 0;
        }
        return particulierCountryID > 0;
      default:
        return false;
    }
  }, [
    selectedType, selectedCompany, showManualCompanyForm,
    manualCompanyName, manualPostalCode, manualCity,
    creationCountryID, creationPostalCode, creationCity,
    foreignCompanyName, foreignCountry,
    particulierCountryID, particulierPostalCode, particulierCity
  ]);

  // ===== HANDLERS =====
  const handleNext = () => {
    if (!isValid) return;

    const data: ProfileData = { type: selectedType };
    let info_datalayer = 'unknown';

    switch (selectedType) {
      case "pro_france":
        data.type_societe = 1;
        if (showManualCompanyForm) {
          data.countryID = 1;
          data.companyName = manualCompanyName;
          data.postalCode = manualPostalCode;
          data.city = manualCity;
        } else {
          data.countryID = 1;
          data.companyName = selectedCompany?.name;
          data.postalCode = selectedCompany?.postalCode;
          data.city = selectedCompany?.city;
          data.siren = selectedCompany?.siren;
          data.siret = selectedCompany?.siret;
          data.naf = selectedCompany?.naf;
          data.address = selectedCompany?.address;
        }
        info_datalayer = 'pro_france';
        break;

      case "creation":
        data.type_societe = 4;
        data.country = creationCountry;
        data.countryID = creationCountryID;
        if (creationCountryID === 1) {
          data.postalCode = creationPostalCode;
          data.city = creationCity;
        }
        info_datalayer = 'creation_societe';
        break;

      case "particulier":
        data.type_societe = 3;
        data.country = particulierCountry;
        data.countryID = particulierCountryID;
        if (particulierCountryID === 1) {
          data.postalCode = particulierPostalCode;
          data.city = particulierCity;
        }
        info_datalayer = 'particulier';
        break;

      case "pro_foreign":
        data.type_societe = 2;
        data.companyName = foreignCompanyName;
        data.country = foreignCountry;
        data.countryID = foreignCountryID;
        info_datalayer = 'pro_etranger';
        break;
    }

    // Persister dans le store Zustand (sessionStorage)
    setProfileData(data);

    // Track profile complete
    trackProfileComplete(info_datalayer);

    onComplete(data);
  };

  const handleSelectCompany = (company: SirenCompanyData) => {
    const companyResult: CompanyResult = {
      siren: company.siren,
      siret: company.siret,
      name: company.name,
      address: company.address,
      postalCode: company.postalCode,
      city: company.city,
      naf: company.naf,
    };
    setSelectedCompany(companyResult);
    setSearchQuery(company.name);
  };

  const handleSelectType = (type: ProfileType) => {
    setSelectedType(type);
    // Reset pro_france specific state
    if (type === "pro_france") {
      setSelectedCompany(null);
      setSearchQuery("");
      setShowManualCompanyForm(false);
      setManualCompanyName("");
      setManualPostalCode("");
      setManualCity("");
    }
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

                {/* Reassurance banner */}
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
                <ProfileOption
                  isSelected={selectedType === "pro_france"}
                  onClick={() => handleSelectType("pro_france")}
                  icon={<Building2 className="h-5 w-5 text-primary shrink-0" />}
                  title="Professionnel basé en France"
                  subtitle="(entreprises, associations, collectivités...)"
                  isPrimary
                >
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

                            <PostalCodeCityInput
                              postalCode={manualPostalCode}
                              city={manualCity}
                              onPostalCodeChange={setManualPostalCode}
                              onCityChange={setManualCity}
                              onSelect={(pc, c) => {
                                setManualPostalCode(pc);
                                setManualCity(c);
                              }}
                              enabled={showManualCompanyForm}
                            />
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
                </ProfileOption>

                {/* Option 2: Company being created */}
                <ProfileOption
                  isSelected={selectedType === "creation"}
                  onClick={() => setSelectedType("creation")}
                  icon={<Sparkles className="h-5 w-5 text-muted-foreground shrink-0" />}
                  title="Société en cours de création"
                >
                  {selectedType === "creation" && (
                    <div className="mt-4 ml-8 space-y-3">
                      <p className="text-sm text-muted-foreground">Merci de renseigner votre localisation</p>

                      <CountrySelector
                        value={creationCountry}
                        valueId={creationCountryID}
                        onChange={(country, id) => {
                          setCreationCountry(country);
                          setCreationCountryID(id);
                          // Reset postal code when country changes
                          setCreationPostalCode("");
                          setCreationCity("");
                        }}
                        countries={allCountries}
                        priorityCountries={priorityCountries}
                        showFranceFirst
                      />

                      {creationCountryID === 1 && (
                        <PostalCodeCityInput
                          postalCode={creationPostalCode}
                          city={creationCity}
                          onPostalCodeChange={setCreationPostalCode}
                          onCityChange={setCreationCity}
                          onSelect={(pc, c) => {
                            setCreationPostalCode(pc);
                            setCreationCity(c);
                          }}
                          enabled={selectedType === "creation"}
                        />
                      )}
                    </div>
                  )}
                </ProfileOption>

                {/* Option 3: Professional outside France */}
                <ProfileOption
                  isSelected={selectedType === "pro_foreign"}
                  onClick={() => setSelectedType("pro_foreign")}
                  icon={<Globe className="h-5 w-5 text-muted-foreground shrink-0" />}
                  title="Professionnel hors de France"
                >
                  {selectedType === "pro_foreign" && (
                    <div className="mt-4 ml-8 space-y-3">
                      <p className="text-sm text-muted-foreground">Merci de renseigner vos informations</p>
                      <div className="space-y-3">
                        <div>
                          <label className="text-sm text-muted-foreground">Votre structure</label>
                          <input
                            type="text"
                            value={foreignCompanyName}
                            onChange={(e) => setForeignCompanyName(e.target.value)}
                            placeholder="Nom de votre société / association / collectivité..."
                            className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                          />
                        </div>

                        <CountrySelector
                          value={foreignCountry}
                          valueId={foreignCountryID}
                          onChange={(country, id) => {
                            setForeignCountry(country);
                            setForeignCountryID(id);
                          }}
                          countries={allCountries}
                          priorityCountries={priorityCountries}
                          excludeFrance
                        />
                      </div>
                    </div>
                  )}
                </ProfileOption>

                {/* Option 4: Individual */}
                <ProfileOption
                  isSelected={selectedType === "particulier"}
                  onClick={() => setSelectedType("particulier")}
                  icon={<User className="h-5 w-5 text-muted-foreground shrink-0" />}
                  title="Particulier"
                >
                  {selectedType === "particulier" && (
                    <div className="mt-4 ml-8 space-y-3">
                      <p className="text-sm text-muted-foreground">Merci de renseigner votre localisation</p>

                      <CountrySelector
                        value={particulierCountry}
                        valueId={particulierCountryID}
                        onChange={(country, id) => {
                          setParticulierCountry(country);
                          setParticulierCountryID(id);
                          // Reset postal code when country changes
                          setParticulierPostalCode("");
                          setParticulierCity("");
                        }}
                        countries={allCountries}
                        priorityCountries={priorityCountries}
                        showFranceFirst
                      />

                      {particulierCountryID === 1 && (
                        <PostalCodeCityInput
                          postalCode={particulierPostalCode}
                          city={particulierCity}
                          onPostalCodeChange={setParticulierPostalCode}
                          onCityChange={setParticulierCity}
                          onSelect={(pc, c) => {
                            setParticulierPostalCode(pc);
                            setParticulierCity(c);
                          }}
                          enabled={selectedType === "particulier" && particulierCountryID === 1}
                        />
                      )}
                    </div>
                  )}
                </ProfileOption>
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

// ===== SUB-COMPONENT: Profile Option =====
interface ProfileOptionProps {
  isSelected: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  isPrimary?: boolean;
  children?: React.ReactNode;
}

const ProfileOption = ({
  isSelected,
  onClick,
  icon,
  title,
  subtitle,
  isPrimary = false,
  children,
}: ProfileOptionProps) => (
  <div
    className={cn(
      "rounded-xl border-2 p-4 transition-all",
      isSelected
        ? "border-primary bg-primary/5"
        : "border-border hover:border-primary/50"
    )}
  >
    <button onClick={onClick} className="w-full text-left">
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors mt-0.5",
            isSelected
              ? "border-primary bg-primary"
              : "border-muted-foreground/30"
          )}
        >
          {isSelected && (
            <div className="h-2 w-2 rounded-full bg-primary-foreground" />
          )}
        </div>
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            {icon}
            <span className={cn("font-medium", isPrimary ? "text-primary" : "text-foreground")}>
              {title}
            </span>
          </div>
          {subtitle && (
            <span className="text-sm text-muted-foreground">{subtitle}</span>
          )}
        </div>
      </div>
    </button>
    {children}
  </div>
);

export default ProfileTypeStep;
