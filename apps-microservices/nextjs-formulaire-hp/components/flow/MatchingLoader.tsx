"use client";

import { useState, useEffect } from "react";
import { Search, Package, Truck, CheckCircle2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

interface MatchingLoaderProps {
  onComplete: () => void;
  duration?: number; // in milliseconds
}

const STEPS = [
  {
    icon: Search,
    title: "Analyse de vos critères",
    subtitle: "Identification de vos besoins spécifiques",
  },
  {
    icon: Package,
    title: "Recherche des produits",
    subtitle: "Parcours de notre catalogue de 2 400+ références",
  },
  {
    icon: Truck,
    title: "Sélection des fournisseurs",
    subtitle: "Vérification des zones de livraison et disponibilités",
  },
  {
    icon: CheckCircle2,
    title: "Finalisation",
    subtitle: "Préparation de votre sélection personnalisée",
  },
];

const MatchingLoader = ({ onComplete, duration = 5000 }: MatchingLoaderProps) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [progress, setProgress] = useState(0);
  const [isComplete, setIsComplete] = useState(false);

  const stepDuration = duration / STEPS.length;

  useEffect(() => {
    // Progress bar animation
    const progressInterval = setInterval(() => {
      setProgress((prev) => {
        const newProgress = prev + (100 / (duration / 50));
        return Math.min(newProgress, 100);
      });
    }, 50);

    // Step transitions
    const stepTimer = setInterval(() => {
      setCurrentStep((prev) => {
        if (prev < STEPS.length - 1) {
          return prev + 1;
        }
        return prev;
      });
    }, stepDuration);

    // Complete after duration
    const completeTimer = setTimeout(() => {
      setIsComplete(true);
      setTimeout(onComplete, 500); // Small delay for exit animation
    }, duration);

    return () => {
      clearInterval(progressInterval);
      clearInterval(stepTimer);
      clearTimeout(completeTimer);
    };
  }, [duration, stepDuration, onComplete]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
      {/* Animated background */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-primary/10 via-background to-background" />

        {/* Floating particles */}
        <div className="absolute inset-0">
          {[...Array(20)].map((_, i) => (
            <div
              key={i}
              className="absolute h-2 w-2 rounded-full bg-primary/20"
              style={{
                left: `${Math.random() * 100}%`,
                top: `${Math.random() * 100}%`,
                animation: `float ${3 + Math.random() * 4}s ease-in-out infinite`,
                animationDelay: `${Math.random() * 2}s`,
              }}
            />
          ))}
        </div>
      </div>

      <div
        className={cn(
          "relative z-10 w-full max-w-lg px-6 transition-all duration-500",
          isComplete ? "opacity-0 scale-95" : "opacity-100 scale-100"
        )}
      >
        {/* Logo / Brand icon */}
        <div className="flex justify-center mb-8">
          <div className="relative">
            <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-primary/10 border border-primary/20">
              <Sparkles className="h-10 w-10 text-primary animate-pulse" />
            </div>
            {/* Rotating ring */}
            <div className="absolute -inset-3 rounded-3xl border-2 border-primary/30 border-t-primary animate-spin" style={{ animationDuration: '2s' }} />
          </div>
        </div>

        {/* Title */}
        <div className="text-center mb-10">
          <h2 className="text-2xl font-bold text-foreground mb-2">
            Recherche en cours...
          </h2>
          <p className="text-muted-foreground">
            Nous analysons les meilleurs fournisseurs pour vous
          </p>
        </div>

        {/* Steps */}
        <div className="space-y-4 mb-8">
          {STEPS.map((step, index) => {
            const Icon = step.icon;
            const isActive = index === currentStep;
            const isCompleted = index < currentStep;

            return (
              <div
                key={index}
                className={cn(
                  "flex items-center gap-4 rounded-xl p-4 transition-all duration-500",
                  isActive && "bg-primary/10 border border-primary/20 shadow-lg shadow-primary/5",
                  isCompleted && "opacity-60",
                  !isActive && !isCompleted && "opacity-30"
                )}
              >
                <div
                  className={cn(
                    "flex h-12 w-12 items-center justify-center rounded-xl transition-all duration-300",
                    isActive && "bg-primary text-primary-foreground scale-110",
                    isCompleted && "bg-match-high/20 text-match-high",
                    !isActive && !isCompleted && "bg-muted text-muted-foreground"
                  )}
                >
                  {isCompleted ? (
                    <CheckCircle2 className="h-6 w-6" />
                  ) : (
                    <Icon className={cn("h-6 w-6", isActive && "animate-pulse")} />
                  )}
                </div>

                <div className="flex-1">
                  <p
                    className={cn(
                      "font-semibold transition-colors duration-300",
                      isActive ? "text-foreground" : "text-muted-foreground"
                    )}
                  >
                    {step.title}
                  </p>
                  <p
                    className={cn(
                      "text-sm transition-colors duration-300",
                      isActive ? "text-muted-foreground" : "text-muted-foreground/60"
                    )}
                  >
                    {step.subtitle}
                  </p>
                </div>

                {isActive && (
                  <div className="flex gap-1">
                    <span className="h-2 w-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="h-2 w-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="h-2 w-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Progress bar */}
        <div className="space-y-2">
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full bg-gradient-to-r from-primary to-accent transition-all duration-100 ease-linear rounded-full"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-center text-sm text-muted-foreground">
            {Math.round(progress)}% complété
          </p>
        </div>
      </div>

      {/* CSS for floating animation */}
      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0) translateX(0); opacity: 0.2; }
          25% { transform: translateY(-20px) translateX(10px); opacity: 0.5; }
          50% { transform: translateY(-10px) translateX(-10px); opacity: 0.3; }
          75% { transform: translateY(-30px) translateX(5px); opacity: 0.4; }
        }
      `}</style>
    </div>
  );
};

export default MatchingLoader;
