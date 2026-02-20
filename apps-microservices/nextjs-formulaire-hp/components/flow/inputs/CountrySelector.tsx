'use client';

import { useState, useMemo } from "react";
import { Globe, Search } from "lucide-react";
import { cn } from "@/lib/utils";

interface Country {
  id: number;
  libelle: string;
}

interface CountrySelectorProps {
  value: string;
  valueId: number;
  onChange: (country: string, countryId: number) => void;
  countries: Country[];
  priorityCountries?: Country[];
  excludeFrance?: boolean;
  showFranceFirst?: boolean;
  placeholder?: string;
  label?: string;
}

const CountrySelector = ({
  value,
  valueId,
  onChange,
  countries,
  priorityCountries = [],
  excludeFrance = false,
  showFranceFirst = false,
  placeholder = "Sélectionner un pays",
  label = "Pays",
}: CountrySelectorProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");

  // Build country list with optional priority section
  const allCountries = useMemo(() => {
    const priorityIds = new Set(priorityCountries.map((c) => c.libelle));
    const filtered = countries.filter((c) => !priorityIds.has(c.libelle));
    return [...priorityCountries, ...filtered];
  }, [countries, priorityCountries]);

  // Filter countries based on search and excludeFrance option
  const filteredCountries = useMemo(() => {
    let list = allCountries;

    if (excludeFrance) {
      list = list.filter((c) => c.libelle !== "France");
    }

    if (!search.trim()) return list;

    return list.filter((c) =>
      c.libelle.toLowerCase().includes(search.toLowerCase())
    );
  }, [search, allCountries, excludeFrance]);

  const handleSelect = (country: Country) => {
    onChange(country.libelle, country.id);
    setIsOpen(false);
    setSearch("");
  };

  const handleFranceSelect = () => {
    onChange("France", 1);
    setIsOpen(false);
    setSearch("");
  };

  return (
    <div className="relative">
      {label && (
        <label className="text-sm text-muted-foreground">{label}</label>
      )}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="mt-1 w-full flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-left focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
      >
        <span className={value ? "text-foreground" : "text-muted-foreground"}>
          {value || placeholder}
        </span>
        <Globe className="h-4 w-4 text-muted-foreground" />
      </button>

      {isOpen && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-border bg-card shadow-lg max-h-64 overflow-hidden">
          {/* Search input */}
          <div className="p-2 border-b border-border">
            <div className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
              <Search className="h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Rechercher un pays..."
                className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                autoFocus
              />
            </div>
          </div>

          {/* Country list */}
          <div className="max-h-48 overflow-y-auto">
            {/* France first option if enabled */}
            {showFranceFirst && !excludeFrance && (
              <button
                onClick={handleFranceSelect}
                className={cn(
                  "w-full text-left px-4 py-2.5 text-sm hover:bg-muted transition-colors border-b border-border",
                  valueId === 1 && "bg-primary/10 text-primary font-medium"
                )}
              >
                France
              </button>
            )}

            {/* Filtered countries */}
            {filteredCountries.map((country) => (
              <button
                key={country.id}
                onClick={() => handleSelect(country)}
                className={cn(
                  "w-full text-left px-4 py-2.5 text-sm hover:bg-muted transition-colors",
                  valueId === country.id && "bg-primary/10 text-primary font-medium"
                )}
              >
                {country.libelle}
              </button>
            ))}

            {filteredCountries.length === 0 && (
              <div className="px-4 py-3 text-sm text-muted-foreground text-center">
                Aucun pays trouvé
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default CountrySelector;
