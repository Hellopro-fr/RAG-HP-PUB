import { useState, useEffect } from "react";
import { searchPostalCodeCities, type PostalCodeCity } from "@/lib/api/services/postalCode.service";

interface UsePostalCodeSearchProps {
  query: string;
  enabled?: boolean;
}

export function usePostalCodeSearch({
  query,
  enabled = true,
}: UsePostalCodeSearchProps) {
  const [data, setData] = useState<PostalCodeCity[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  

  useEffect(() => {

    setIsLoading(true);


    if (!enabled || query.length < 3) {
      setData([]);
      setError(null);
      setIsLoading(false);
      return;
    }

    const fetchData = async () => {
      setError(null);
      try {
        const results = await searchPostalCodeCities(query);
        setData(results);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Erreur lors de la recherche"
        );
        setData([]);
      } finally {
        setIsLoading(false);
      }
    };

    // Debounce de 300ms pour éviter trop d'appels API
    const timer = setTimeout(fetchData, 300);

    return () => clearTimeout(timer);
  }, [query, enabled]);

  return { data, isLoading, error };
}