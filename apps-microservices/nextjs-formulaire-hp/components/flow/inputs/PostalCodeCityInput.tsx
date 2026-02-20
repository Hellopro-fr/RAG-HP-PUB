'use client';

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { usePostalCodeSearch } from "@/hooks/usePostalCodeSearch";

interface PostalCodeCityInputProps {
  postalCode: string;
  city: string;
  onPostalCodeChange: (postalCode: string) => void;
  onCityChange: (city: string) => void;
  onSelect: (postalCode: string, city: string) => void;
  enabled?: boolean;
  postalCodeLabel?: string;
  cityLabel?: string;
  postalCodePlaceholder?: string;
  cityPlaceholder?: string;
}

const PostalCodeCityInput = ({
  postalCode,
  city,
  onPostalCodeChange,
  onCityChange,
  onSelect,
  enabled = true,
  postalCodeLabel = "Code postal",
  cityLabel = "Ville",
  postalCodePlaceholder = "75001",
  cityPlaceholder = "Paris",
}: PostalCodeCityInputProps) => {
  const [showSuggestions, setShowSuggestions] = useState(false);

  // Postal code search via API
  const { data: suggestions, isLoading } = usePostalCodeSearch({
    query: postalCode,
    enabled: enabled && postalCode.length >= 3 && !city,
  });

  const handlePostalCodeChange = (value: string) => {
    // Only allow digits, max 5 characters
    const cleaned = value.replace(/\D/g, "").slice(0, 5);
    onPostalCodeChange(cleaned);
    onCityChange(""); // Reset city when postal code changes
    setShowSuggestions(cleaned.length >= 1);
  };

  const handleSelectSuggestion = (item: { postalCode: string; city: string }) => {
    onSelect(item.postalCode, item.city);
    setShowSuggestions(false);
  };

  const displayedSuggestions = suggestions.slice(0, 8);

  return (
    <div className="grid grid-cols-2 gap-3">
      {/* Postal Code */}
      <div className="relative">
        <label className="text-sm text-muted-foreground">{postalCodeLabel}</label>
        <input
          type="text"
          value={postalCode}
          onChange={(e) => handlePostalCodeChange(e.target.value)}
          onFocus={() => postalCode.length >= 2 && setShowSuggestions(true)}
          onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
          placeholder={postalCodePlaceholder}
          className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />

        {/* Suggestions dropdown */}
        {showSuggestions && postalCode.length >= 1 && !city && (
          <div className="absolute z-50 mt-1 w-[calc(200%+0.75rem)] rounded-lg border border-border bg-card shadow-lg max-h-48 overflow-y-auto">
            {isLoading ? (
              <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Recherche...
              </div>
            ) : displayedSuggestions.length > 0 ? (
              displayedSuggestions.map((item, index) => (
                <button
                  key={`${item.postalCode}-${item.city}-${index}`}
                  onClick={() => handleSelectSuggestion(item)}
                  className={cn(
                    "w-full text-left px-4 py-2.5 text-sm hover:bg-muted transition-colors",
                    index === 0 && "rounded-t-lg",
                    index === displayedSuggestions.length - 1 && "rounded-b-lg"
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

      {/* City */}
      <div>
        <label className="text-sm text-muted-foreground">{cityLabel}</label>
        <input
          type="text"
          value={city}
          onChange={(e) => onCityChange(e.target.value)}
          placeholder={cityPlaceholder}
          className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
      </div>
    </div>
  );
};

export default PostalCodeCityInput;
