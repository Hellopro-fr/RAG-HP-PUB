'use client';

import { Check, X, Phone } from "lucide-react";
import Image from "next/image";
import { cn, getAssetPath } from "@/lib/utils";
const hpLogo = getAssetPath("/images/hp-logo.svg");
const expertPhoto = getAssetPath("/images/expert-patrick.jpg");

interface Step {
  id: number;
  label: string;
}

interface ProgressHeaderProps {
  steps: Step[];
  currentStep: number;
  progress: number;
  showSteps?: boolean;
  showExpertHelp?: boolean;
  showProgressBar?: boolean;
}

const ProgressHeader = ({ steps, currentStep, progress, showSteps = true, showExpertHelp = true, showProgressBar = true }: ProgressHeaderProps) => {
  const currentStepData = steps.find(s => s.id === currentStep);
  
  return (
    <div className="border-b border-border bg-card">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 lg:px-6 lg:py-4">
        {/* Logo */}
        <Image src={hpLogo} alt="Hellopro" width={120} height={32} className="h-5 lg:h-8 w-auto shrink-0" />

        {/* Mobile/Tablet: Current step indicator - simplified */}
        {showSteps && (
        <div className="flex lg:hidden items-center gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">
            Étape {currentStep}/{steps.length}
          </span>
          <span className="text-xs text-foreground">
            · {currentStepData?.label}
          </span>
        </div>
        )}

        {/* Desktop: Full steps */}
        {showSteps && (
        <div className="hidden lg:flex items-center gap-6">
          {steps.map((step, index) => (
            <div key={step.id} className="flex items-center gap-2">
              <div
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium transition-colors",
                  step.id < currentStep
                    ? "bg-primary text-primary-foreground"
                    : step.id === currentStep
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground"
                )}
              >
                {step.id < currentStep ? (
                  <Check className="h-3.5 w-3.5" />
                ) : (
                  step.id
                )}
              </div>
              <span
                className={cn(
                  "text-sm font-medium whitespace-nowrap",
                  step.id <= currentStep
                    ? "text-foreground"
                    : "text-muted-foreground"
                )}
              >
                {step.label}
              </span>
              {index < steps.length - 1 && (
                <div className="ml-4 h-px w-8 bg-border" />
              )}
            </div>
          ))}
        </div>
        )}

        {/* Expert help - desktop */}
        {showExpertHelp && (
        <a
          href="tel:+33745882953"
          className="hidden lg:flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <Image
            src={expertPhoto}
            alt="Patrick Duval"
            width={28}
            height={28}
            className="h-7 w-7 rounded-full object-cover ring-1 ring-border"
          />
          <span className="text-xs">Besoin d'aide ?</span>
          <span className="font-medium text-foreground">07 45 88 29 53</span>
        </a>
        )}

        {/* Expert help - mobile/tablet (icon only) */}
        {showExpertHelp && (
        <a
          href="tel:+33745882953"
          className="lg:hidden flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors"
        >
          <Image
            src={expertPhoto}
            alt="Patrick Duval"
            width={24}
            height={24}
            className="h-6 w-6 rounded-full object-cover ring-1 ring-border"
          />
          <Phone className="h-4 w-4 text-primary" />
        </a>
        )}
      </div>

      {/* Progress Bar */}
      {showProgressBar && (
      <div className="h-1 w-full bg-muted">
        <div
          className="h-full bg-primary transition-all duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>
      )}
    </div>
  );
};

export default ProgressHeader;
