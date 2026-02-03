'use client';

import { useState } from "react";
import { ThumbsUp, ThumbsDown, Mail, MessageCircle, X, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "@/hooks/use-toast";

interface SelectionFeedbackProps {
  selectedCount: number;
  onSaveSelection?: (email: string) => void;
  onReportProblem?: (message: string) => void;
}

const SelectionFeedback = ({ 
  selectedCount, 
  onSaveSelection,
  onReportProblem 
}: SelectionFeedbackProps) => {
  const [feedbackGiven, setFeedbackGiven] = useState<"positive" | "negative" | null>(null);
  const [showEmailForm, setShowEmailForm] = useState(false);
  const [showProblemForm, setShowProblemForm] = useState(false);
  const [email, setEmail] = useState("");
  const [problemMessage, setProblemMessage] = useState("");

  const handlePositiveFeedback = () => {
    setFeedbackGiven("positive");
    toast({
      title: "Merci pour votre retour !",
      description: "Nous sommes ravis que cette sélection vous convienne.",
    });
  };

  const handleNegativeFeedback = () => {
    setFeedbackGiven("negative");
    setShowProblemForm(true);
  };

  const handleSaveSelection = () => {
    if (email && email.includes("@")) {
      onSaveSelection?.(email);
      setShowEmailForm(false);
      setEmail("");
      toast({
        title: "Sélection envoyée !",
        description: `Un récapitulatif a été envoyé à ${email}`,
      });
    }
  };

  const handleReportProblem = () => {
    if (problemMessage.trim()) {
      onReportProblem?.(problemMessage);
      setShowProblemForm(false);
      setProblemMessage("");
      setFeedbackGiven("negative");
      toast({
        title: "Merci pour votre retour",
        description: "Nous allons améliorer notre sélection.",
      });
    }
  };

  return (
    <div className="border-t border-border bg-muted/30 px-4 py-3 sm:px-6">
      <div className="mx-auto max-w-7xl">
        {/* Email Form Modal */}
        {showEmailForm && (
          <div className="mb-4 p-4 bg-background rounded-lg border border-border shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-medium text-foreground">
                Recevoir ma sélection par email
              </h4>
              <button 
                onClick={() => setShowEmailForm(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex gap-2">
              <input
                type="email"
                placeholder="votre@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
              <button
                onClick={handleSaveSelection}
                disabled={!email || !email.includes("@")}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Envoyer
              </button>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Recevez un récapitulatif des {selectedCount} produit{selectedCount > 1 ? "s" : ""} sélectionné{selectedCount > 1 ? "s" : ""} pour y revenir plus tard.
            </p>
          </div>
        )}

        {/* Problem Form Modal */}
        {showProblemForm && (
          <div className="mb-4 p-4 bg-background rounded-lg border border-border shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-medium text-foreground">
                Qu'est-ce qui ne vous a pas convenu ?
              </h4>
              <button 
                onClick={() => {
                  setShowProblemForm(false);
                  setFeedbackGiven(null);
                }}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {[
                  "Prix trop élevés",
                  "Pas assez de choix",
                  "Produits inadaptés",
                  "Manque d'informations",
                  "Autre"
                ].map((reason) => (
                  <button
                    key={reason}
                    onClick={() => setProblemMessage(reason)}
                    className={cn(
                      "rounded-full px-3 py-1.5 text-xs font-medium border transition-colors",
                      problemMessage === reason
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-background text-foreground border-border hover:border-primary/50"
                    )}
                  >
                    {reason}
                  </button>
                ))}
              </div>
              <textarea
                placeholder="Donnez-nous plus de détails (optionnel)..."
                value={problemMessage.startsWith("Prix") || problemMessage.startsWith("Pas") || problemMessage.startsWith("Produits") || problemMessage.startsWith("Manque") || problemMessage === "Autre" ? "" : problemMessage}
                onChange={(e) => setProblemMessage(e.target.value)}
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 resize-none h-20"
              />
              <button
                onClick={handleReportProblem}
                disabled={!problemMessage.trim()}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Envoyer mon retour
              </button>
            </div>
          </div>
        )}

        {/* Feedback Bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          {/* Left: Save selection */}
          <button
            onClick={() => setShowEmailForm(true)}
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <Mail className="h-4 w-4" />
            <span>Sauvegarder ma sélection</span>
          </button>

          {/* Center: Micro feedback */}
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground">Cette sélection vous convient ?</span>
            <div className="flex items-center gap-1">
              <button
                onClick={handlePositiveFeedback}
                className={cn(
                  "p-1.5 rounded-full transition-colors",
                  feedbackGiven === "positive"
                    ? "bg-green-100 text-green-600"
                    : "text-muted-foreground hover:text-green-600 hover:bg-green-50"
                )}
                title="Oui, c'est pertinent"
              >
                {feedbackGiven === "positive" ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <ThumbsUp className="h-4 w-4" />
                )}
              </button>
              <button
                onClick={handleNegativeFeedback}
                className={cn(
                  "p-1.5 rounded-full transition-colors",
                  feedbackGiven === "negative"
                    ? "bg-red-100 text-red-600"
                    : "text-muted-foreground hover:text-red-600 hover:bg-red-50"
                )}
                title="Non, pas vraiment"
              >
                <ThumbsDown className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Right: Report problem */}
          <button
            onClick={() => setShowProblemForm(true)}
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <MessageCircle className="h-4 w-4" />
            <span>Pas trouvé ce que vous cherchez ?</span>
          </button>
        </div>
      </div>
    </div>
  );
};

export default SelectionFeedback;
