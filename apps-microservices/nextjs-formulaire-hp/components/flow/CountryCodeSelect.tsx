'use client';

import { useState, useRef, useEffect } from "react";
import { Search, ChevronDown } from "lucide-react";

const COUNTRY_CODES = [
  { code: "+93", country: "Afghanistan", flag: "🇦🇫" },
  { code: "+355", country: "Albanie", flag: "🇦🇱" },
  { code: "+213", country: "Algérie", flag: "🇩🇿" },
  { code: "+376", country: "Andorre", flag: "🇦🇩" },
  { code: "+244", country: "Angola", flag: "🇦🇴" },
  { code: "+54", country: "Argentine", flag: "🇦🇷" },
  { code: "+374", country: "Arménie", flag: "🇦🇲" },
  { code: "+61", country: "Australie", flag: "🇦🇺" },
  { code: "+43", country: "Autriche", flag: "🇦🇹" },
  { code: "+994", country: "Azerbaïdjan", flag: "🇦🇿" },
  { code: "+973", country: "Bahreïn", flag: "🇧🇭" },
  { code: "+880", country: "Bangladesh", flag: "🇧🇩" },
  { code: "+32", country: "Belgique", flag: "🇧🇪" },
  { code: "+229", country: "Bénin", flag: "🇧🇯" },
  { code: "+975", country: "Bhoutan", flag: "🇧🇹" },
  { code: "+591", country: "Bolivie", flag: "🇧🇴" },
  { code: "+387", country: "Bosnie-Herzégovine", flag: "🇧🇦" },
  { code: "+267", country: "Botswana", flag: "🇧🇼" },
  { code: "+55", country: "Brésil", flag: "🇧🇷" },
  { code: "+359", country: "Bulgarie", flag: "🇧🇬" },
  { code: "+226", country: "Burkina Faso", flag: "🇧🇫" },
  { code: "+257", country: "Burundi", flag: "🇧🇮" },
  { code: "+855", country: "Cambodge", flag: "🇰🇭" },
  { code: "+237", country: "Cameroun", flag: "🇨🇲" },
  { code: "+1", country: "Canada", flag: "🇨🇦" },
  { code: "+238", country: "Cap-Vert", flag: "🇨🇻" },
  { code: "+236", country: "Centrafrique", flag: "🇨🇫" },
  { code: "+56", country: "Chili", flag: "🇨🇱" },
  { code: "+86", country: "Chine", flag: "🇨🇳" },
  { code: "+357", country: "Chypre", flag: "🇨🇾" },
  { code: "+57", country: "Colombie", flag: "🇨🇴" },
  { code: "+269", country: "Comores", flag: "🇰🇲" },
  { code: "+242", country: "Congo", flag: "🇨🇬" },
  { code: "+243", country: "Congo (RDC)", flag: "🇨🇩" },
  { code: "+82", country: "Corée du Sud", flag: "🇰🇷" },
  { code: "+225", country: "Côte d'Ivoire", flag: "🇨🇮" },
  { code: "+385", country: "Croatie", flag: "🇭🇷" },
  { code: "+53", country: "Cuba", flag: "🇨🇺" },
  { code: "+45", country: "Danemark", flag: "🇩🇰" },
  { code: "+253", country: "Djibouti", flag: "🇩🇯" },
  { code: "+20", country: "Égypte", flag: "🇪🇬" },
  { code: "+971", country: "Émirats arabes unis", flag: "🇦🇪" },
  { code: "+593", country: "Équateur", flag: "🇪🇨" },
  { code: "+34", country: "Espagne", flag: "🇪🇸" },
  { code: "+372", country: "Estonie", flag: "🇪🇪" },
  { code: "+1", country: "États-Unis", flag: "🇺🇸" },
  { code: "+251", country: "Éthiopie", flag: "🇪🇹" },
  { code: "+358", country: "Finlande", flag: "🇫🇮" },
  { code: "+33", country: "France", flag: "🇫🇷" },
  { code: "+241", country: "Gabon", flag: "🇬🇦" },
  { code: "+220", country: "Gambie", flag: "🇬🇲" },
  { code: "+995", country: "Géorgie", flag: "🇬🇪" },
  { code: "+233", country: "Ghana", flag: "🇬🇭" },
  { code: "+30", country: "Grèce", flag: "🇬🇷" },
  { code: "+502", country: "Guatemala", flag: "🇬🇹" },
  { code: "+224", country: "Guinée", flag: "🇬🇳" },
  { code: "+509", country: "Haïti", flag: "🇭🇹" },
  { code: "+504", country: "Honduras", flag: "🇭🇳" },
  { code: "+852", country: "Hong Kong", flag: "🇭🇰" },
  { code: "+36", country: "Hongrie", flag: "🇭🇺" },
  { code: "+91", country: "Inde", flag: "🇮🇳" },
  { code: "+62", country: "Indonésie", flag: "🇮🇩" },
  { code: "+98", country: "Iran", flag: "🇮🇷" },
  { code: "+964", country: "Irak", flag: "🇮🇶" },
  { code: "+353", country: "Irlande", flag: "🇮🇪" },
  { code: "+354", country: "Islande", flag: "🇮🇸" },
  { code: "+972", country: "Israël", flag: "🇮🇱" },
  { code: "+39", country: "Italie", flag: "🇮🇹" },
  { code: "+81", country: "Japon", flag: "🇯🇵" },
  { code: "+962", country: "Jordanie", flag: "🇯🇴" },
  { code: "+7", country: "Kazakhstan", flag: "🇰🇿" },
  { code: "+254", country: "Kenya", flag: "🇰🇪" },
  { code: "+965", country: "Koweït", flag: "🇰🇼" },
  { code: "+996", country: "Kirghizistan", flag: "🇰🇬" },
  { code: "+856", country: "Laos", flag: "🇱🇦" },
  { code: "+371", country: "Lettonie", flag: "🇱🇻" },
  { code: "+961", country: "Liban", flag: "🇱🇧" },
  { code: "+218", country: "Libye", flag: "🇱🇾" },
  { code: "+423", country: "Liechtenstein", flag: "🇱🇮" },
  { code: "+370", country: "Lituanie", flag: "🇱🇹" },
  { code: "+352", country: "Luxembourg", flag: "🇱🇺" },
  { code: "+853", country: "Macao", flag: "🇲🇴" },
  { code: "+389", country: "Macédoine du Nord", flag: "🇲🇰" },
  { code: "+261", country: "Madagascar", flag: "🇲🇬" },
  { code: "+60", country: "Malaisie", flag: "🇲🇾" },
  { code: "+960", country: "Maldives", flag: "🇲🇻" },
  { code: "+223", country: "Mali", flag: "🇲🇱" },
  { code: "+356", country: "Malte", flag: "🇲🇹" },
  { code: "+212", country: "Maroc", flag: "🇲🇦" },
  { code: "+230", country: "Maurice", flag: "🇲🇺" },
  { code: "+222", country: "Mauritanie", flag: "🇲🇷" },
  { code: "+52", country: "Mexique", flag: "🇲🇽" },
  { code: "+373", country: "Moldavie", flag: "🇲🇩" },
  { code: "+377", country: "Monaco", flag: "🇲🇨" },
  { code: "+976", country: "Mongolie", flag: "🇲🇳" },
  { code: "+382", country: "Monténégro", flag: "🇲🇪" },
  { code: "+258", country: "Mozambique", flag: "🇲🇿" },
  { code: "+95", country: "Myanmar", flag: "🇲🇲" },
  { code: "+264", country: "Namibie", flag: "🇳🇦" },
  { code: "+977", country: "Népal", flag: "🇳🇵" },
  { code: "+505", country: "Nicaragua", flag: "🇳🇮" },
  { code: "+227", country: "Niger", flag: "🇳🇪" },
  { code: "+234", country: "Nigeria", flag: "🇳🇬" },
  { code: "+47", country: "Norvège", flag: "🇳🇴" },
  { code: "+64", country: "Nouvelle-Zélande", flag: "🇳🇿" },
  { code: "+968", country: "Oman", flag: "🇴🇲" },
  { code: "+256", country: "Ouganda", flag: "🇺🇬" },
  { code: "+998", country: "Ouzbékistan", flag: "🇺🇿" },
  { code: "+92", country: "Pakistan", flag: "🇵🇰" },
  { code: "+970", country: "Palestine", flag: "🇵🇸" },
  { code: "+507", country: "Panama", flag: "🇵🇦" },
  { code: "+595", country: "Paraguay", flag: "🇵🇾" },
  { code: "+31", country: "Pays-Bas", flag: "🇳🇱" },
  { code: "+51", country: "Pérou", flag: "🇵🇪" },
  { code: "+63", country: "Philippines", flag: "🇵🇭" },
  { code: "+48", country: "Pologne", flag: "🇵🇱" },
  { code: "+351", country: "Portugal", flag: "🇵🇹" },
  { code: "+974", country: "Qatar", flag: "🇶🇦" },
  { code: "+40", country: "Roumanie", flag: "🇷🇴" },
  { code: "+44", country: "Royaume-Uni", flag: "🇬🇧" },
  { code: "+7", country: "Russie", flag: "🇷🇺" },
  { code: "+250", country: "Rwanda", flag: "🇷🇼" },
  { code: "+221", country: "Sénégal", flag: "🇸🇳" },
  { code: "+381", country: "Serbie", flag: "🇷🇸" },
  { code: "+65", country: "Singapour", flag: "🇸🇬" },
  { code: "+421", country: "Slovaquie", flag: "🇸🇰" },
  { code: "+386", country: "Slovénie", flag: "🇸🇮" },
  { code: "+252", country: "Somalie", flag: "🇸🇴" },
  { code: "+249", country: "Soudan", flag: "🇸🇩" },
  { code: "+94", country: "Sri Lanka", flag: "🇱🇰" },
  { code: "+46", country: "Suède", flag: "🇸🇪" },
  { code: "+41", country: "Suisse", flag: "🇨🇭" },
  { code: "+963", country: "Syrie", flag: "🇸🇾" },
  { code: "+886", country: "Taïwan", flag: "🇹🇼" },
  { code: "+992", country: "Tadjikistan", flag: "🇹🇯" },
  { code: "+255", country: "Tanzanie", flag: "🇹🇿" },
  { code: "+235", country: "Tchad", flag: "🇹🇩" },
  { code: "+420", country: "Tchéquie", flag: "🇨🇿" },
  { code: "+66", country: "Thaïlande", flag: "🇹🇭" },
  { code: "+228", country: "Togo", flag: "🇹🇬" },
  { code: "+216", country: "Tunisie", flag: "🇹🇳" },
  { code: "+993", country: "Turkménistan", flag: "🇹🇲" },
  { code: "+90", country: "Turquie", flag: "🇹🇷" },
  { code: "+380", country: "Ukraine", flag: "🇺🇦" },
  { code: "+598", country: "Uruguay", flag: "🇺🇾" },
  { code: "+58", country: "Venezuela", flag: "🇻🇪" },
  { code: "+84", country: "Vietnam", flag: "🇻🇳" },
  { code: "+967", country: "Yémen", flag: "🇾🇪" },
  { code: "+260", country: "Zambie", flag: "🇿🇲" },
  { code: "+263", country: "Zimbabwe", flag: "🇿🇼" },
];

interface CountryCodeSelectProps {
  value: string;
  onChange: (value: string) => void;
}

const CountryCodeSelect = ({ value, onChange }: CountryCodeSelectProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectedCountry = COUNTRY_CODES.find((c) => c.code === value) || COUNTRY_CODES.find((c) => c.code === "+33");

  const filteredCountries = COUNTRY_CODES.filter(
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

  const handleSelect = (code: string) => {
    onChange(code);
    setIsOpen(false);
    setSearch("");
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 rounded-lg border border-input bg-background px-3 py-3 text-foreground hover:bg-muted/50 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
      >
        <span className="text-lg">{selectedCountry?.flag}</span>
        <span className="text-sm font-medium">{selectedCountry?.code}</span>
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
            {filteredCountries.length === 0 ? (
              <div className="px-4 py-3 text-sm text-muted-foreground text-center">
                Aucun pays trouvé
              </div>
            ) : (
              filteredCountries.map((country) => (
                <button
                  key={`${country.code}-${country.country}`}
                  type="button"
                  onClick={() => handleSelect(country.code)}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-muted/50 transition-colors ${
                    country.code === value ? "bg-primary/10" : ""
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
