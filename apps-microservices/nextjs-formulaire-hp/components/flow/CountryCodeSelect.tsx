'use client';

import { useState, useRef, useEffect } from "react";
import { Search, ChevronDown, Loader2 } from "lucide-react";
import { useCountries, getDefaultCountry, type Country } from "@/hooks/api/useCountries";

interface CountryCodeSelectProps {
  value: string;
  countryId?: number;
  onChange: (code: string, countryId: number) => void;
}

const CountryCodeSelect = ({ value, countryId, onChange }: CountryCodeSelectProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: countries = [], isLoading, isError } = useCountries();

  // Trouver le pays sélectionné
  const defaultCountry = getDefaultCountry();
  const selectedCountry = countries.find((c) => c.id === countryId)
    || countries.find((c) => c.code === value)
    || defaultCountry;

  const filteredCountries = countries.filter(
    (country) =>
      country.country.toLowerCase().includes(search.toLowerCase()) ||
      country.code.includes(search)
  );

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setSearch("");
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  const handleSelect = (country: Country) => {
    onChange(country.code, country.id);
    setIsOpen(false);
    setSearch("");
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        disabled={isLoading}
        className="flex items-center gap-2 rounded-lg border border-input bg-background px-3 py-3 text-foreground hover:bg-muted/50 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <>
            <span className="text-lg">{selectedCountry?.flag}</span>
            <span className="text-sm font-medium">{selectedCountry?.code}</span>
          </>
        )}
        <ChevronDown className="h-4 w-4 text-muted-foreground" />
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-1 w-72 rounded-lg border border-border bg-background shadow-lg z-50">
          {/* Search input */}
          <div className="p-2 border-b border-border">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <input
                ref={inputRef}
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Rechercher un pays..."
                className="w-full rounded-md border border-input bg-background pl-9 pr-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>

          {/* Countries list */}
          <div className="max-h-60 overflow-y-auto">
            {isLoading ? (
              <div className="px-4 py-3 text-sm text-muted-foreground text-center flex items-center justify-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Chargement...
              </div>
            ) : isError ? (
              <div className="px-4 py-3 text-sm text-destructive text-center">
                Erreur de chargement
              </div>
            ) : filteredCountries.length === 0 ? (
              <div className="px-4 py-3 text-sm text-muted-foreground text-center">
                Aucun pays trouvé
              </div>
            ) : (
              filteredCountries.map((country) => (
                <button
                  key={`${country.id}-${country.code}`}
                  type="button"
                  onClick={() => handleSelect(country)}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-muted/50 transition-colors ${
                    country.id === selectedCountry?.id ? "bg-primary/10" : ""
                  }`}
                >
                  <span className="text-lg">{country.flag}</span>
                  <span className="flex-1 text-sm text-foreground">{country.country}</span>
                  <span className="text-sm text-muted-foreground">{country.code}</span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default CountryCodeSelect;
