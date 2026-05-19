'use client';

import { useState } from "react";
import { TrendingUp, Search, ChevronDown, ChevronUp } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PriceItem {
  price: string;       // ex: "2 890 €"
  equipment: string;   // description de l'équipement
  date: string;        // ex: "12/01/2026"
}

interface BudgetEstimateProps {
  /** Label de l'aide (ex: "Aide à l'achat · Estimatif budget") */
  label?: string;
  /** Prix minimum HT */
  priceMin?: string;
  /** Prix maximum HT */
  priceMax?: string;
  /** Nombre de prix sourcés */
  priceCount?: number;
  /** Prix moyen HT (optionnel, pour affichage sur la barre) */
  priceMoy?: string;
  /** Positions normalisées [0‑1] des prix sur la barre */
  pricePositions?: number[];
  /** Texte explicatif du détail */
  detailDescription?: string;
  /** Tableau des prix sourcés */
  priceItems?: PriceItem[];
  /** Callback quand l'utilisateur clique "Ce budget ne correspond pas à mon projet" */
  handleClickNeCorrespondPas?: () => void;
}

// ---------------------------------------------------------------------------
// Helpers de formatage
// ---------------------------------------------------------------------------

/** Formate une date ISO "2025-08-31" en "31/08/2025" */
const formatDateISO = (isoDate: string): string => {
  if (!isoDate) return "";
  const parts = isoDate.split("-");
  if (parts.length !== 3) return isoDate;
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
};

// ---------------------------------------------------------------------------
// Helpers de calcul
// ---------------------------------------------------------------------------

/** Parse un prix formaté (ex: "2 890 €", "3 150 €") en nombre. */
const parsePrice = (priceStr: string): number => {
  // Supprime tout sauf les chiffres et la virgule/point décimal
  const cleaned = priceStr.replace(/[^\d,\.]/g, "").replace(",", ".");
  return parseFloat(cleaned) || 0;
};

/**
 * Calcule les positions normalisées [0-1] de chaque item sur la barre,
 * en se basant sur le min et le max de l'ensemble des prix.
 * Si tous les prix sont identiques, retourne 0.5 pour chaque item.
 */
const computePositions = (items: PriceItem[]): number[] => {
  const values = items.map((item) => parsePrice(item.price));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  if (range === 0) return values.map(() => 0.5);
  return values.map((v) => (v - min) / range);
};

/**
 * Déduit priceMin, priceMax et priceMoy (formatés) depuis une liste d'items.
 */
const computeSummary = (items: PriceItem[]) => {
  const values = items.map((item) => parsePrice(item.price));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const avg = values.reduce((acc, v) => acc + v, 0) / values.length;
  const fmt = (n: number) =>
    new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(n) + " €";
  return { priceMin: fmt(min), priceMax: fmt(max), priceMoy: fmt(Math.round(avg)) };
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const BudgetEstimate = ({
  label = "Aide à l'achat · Estimatif budget",
  priceMin: priceMinProp,
  priceMax: priceMaxProp,
  priceCount: priceCountProp,
  priceMoy: priceMoyProp,
  pricePositions: pricePositionsProp,
  detailDescription,
  priceItems = [],
  handleClickNeCorrespondPas
}: BudgetEstimateProps) => {
  const [showDetail, setShowDetail] = useState(false);

  // Calcul dynamique depuis les items (utilisé si les props ne sont pas fournies)
  const computed = computeSummary(priceItems);
  const computedPositions = computePositions(priceItems);

  const priceMin       = priceMinProp       ?? computed.priceMin;
  const priceMax       = priceMaxProp       ?? computed.priceMax;
  const priceMoy       = priceMoyProp       ?? computed.priceMoy;
  const priceCount     = priceCountProp     ?? priceItems.length;
  const pricePositions = pricePositionsProp ?? computedPositions;

  const resolvedDescription =
    detailDescription ??
    `Hellopro parcourt les catalogues et offres fournisseurs pour vous fournir un estimatif réaliste. Ces ${priceCount} prix concernent des équipements similaires à votre recherche (pont 2 colonnes, 4T, traverse supérieure, 400V). Les écarts s'expliquent par les options, la marque et les conditions de livraison/installation.`;

  return (
    <div className="rounded-xl overflow-hidden border border-border bg-card shadow-sm">
      {/* ------------------------------------------------------------------ */}
      {/* Carte principale                                                    */}
      {/* ------------------------------------------------------------------ */}
      <div className="px-5 py-4 space-y-3">
        {/* Ligne 1 : icône + infos + bouton toggle */}
        <div className="flex flex-col sm:flex-row sm:items-start gap-4 sm:gap-6">
          {/* Icône + texte */}
          <div className="flex items-start gap-3.5 flex-1 min-w-0">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-success/10 mt-0.5">
              <TrendingUp className="h-5 w-5 text-success" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-success tracking-wide mb-1">{label}</p>
              <p className="text-xl font-bold text-foreground">
                {priceMin} – {priceMax}
                <span className="text-xs font-normal text-muted-foreground ml-1">HT</span>
              </p>
              <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1.5">
                <Search className="h-3 w-3 shrink-0" />
                Hellopro a sourcé {priceCount} prix sur le web pour des équipements similaires
              </p>
            </div>
          </div>

          {/* Bouton Voir le détail / Masquer */}
          <button
            onClick={() => setShowDetail(!showDetail)}
            aria-expanded={showDetail}
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:text-primary/80 transition-colors whitespace-nowrap self-start sm:mt-3 underline underline-offset-2"
          >
            {showDetail ? "Masquer" : "Voir le détail"}
            {showDetail ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </button>
        </div>

        {/* Ligne 2 : barre de prix */}
        <div className="pl-0 sm:pl-[3.375rem]">
          <div className="relative h-2.5 w-full rounded-full bg-muted overflow-hidden">
            {/* Plage colorée */}
            <div
              className="absolute inset-y-0 rounded-full bg-success/40"
              style={{ left: "0%", right: "0%" }}
            />
            {/* Points de prix */}
            {pricePositions.map((pos, i) => (
              <div
                key={i}
                className="absolute top-1/2 -translate-y-1/2 h-2.5 w-2.5 rounded-full bg-success border-2 border-card shadow-sm"
                style={{ left: `calc(${pos * 100}% - 5px)` }}
              />
            ))}
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-[10px] text-muted-foreground">{priceMin}</span>
            <span className="text-[10px] text-muted-foreground font-medium">moy. {priceMoy}</span>
            <span className="text-[10px] text-muted-foreground">{priceMax}</span>
          </div>
        </div>

        {/* Ligne 3 : lien budget ne correspond pas — MASQUÉ TEMPORAIREMENT */}
        {false && (
          <div className="pl-0 sm:pl-[3.375rem]">
            <button
              onClick={handleClickNeCorrespondPas}
              className="text-xs text-muted-foreground hover:text-primary transition-colors underline underline-offset-2"
            >
              Ce budget ne correspond pas à mon projet →
            </button>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Panneau de détail (dépliable)                                       */}
      {/* ------------------------------------------------------------------ */}
      {showDetail && (
        <div className="border-t border-border px-5 py-4 space-y-4">
          {/* Description */}
          <p className="text-sm text-muted-foreground">{resolvedDescription}</p>

          {/* Tableau des prix */}
          <div className="rounded-lg border bg-card overflow-hidden overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground whitespace-nowrap">
                    Prix HT
                  </th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">
                    Équipement
                  </th>
                  <th className="px-4 py-2.5 text-right font-medium text-muted-foreground whitespace-nowrap hidden">
                    Date
                  </th>
                </tr>
              </thead>
              <tbody>
                {priceItems.map((item, index) => (
                  <tr
                    key={index}
                    className={`border-b last:border-0 ${index % 2 === 0 ? "bg-card" : "bg-muted/20"}`}
                  >
                    <td className="px-4 py-2.5 font-semibold text-foreground whitespace-nowrap">
                      {item.price}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">
                      {item.equipment}
                    </td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground whitespace-nowrap hidden">
                      {formatDateISO(item.date)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default BudgetEstimate;
