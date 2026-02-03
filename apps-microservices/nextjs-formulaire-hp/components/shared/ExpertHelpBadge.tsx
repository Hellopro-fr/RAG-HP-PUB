"use client";

import { Phone } from "lucide-react";
import Image from "next/image";

interface ExpertHelpBadgeProps {
  variant?: "floating" | "inline";
  className?: string;
}

const ExpertHelpBadge = ({ variant = "floating", className = "" }: ExpertHelpBadgeProps) => {
  const phoneNumber = "01 23 45 67 89";
  const phoneLink = "tel:+33123456789";

  if (variant === "inline") {
    return (
      <a
        href={phoneLink}
        className={`inline-flex items-center gap-3 rounded-full bg-background border border-border px-4 py-2 shadow-sm hover:shadow-md transition-shadow ${className}`}
      >
        <Image
          src="/assets/expert-patrick.jpg"
          alt="Patrick Duval"
          width={32}
          height={32}
          className="h-8 w-8 rounded-full object-cover ring-2 ring-primary/20"
        />
        <div className="flex flex-col">
          <span className="text-xs text-muted-foreground">Besoin d&apos;aide ?</span>
          <span className="text-sm font-medium text-foreground">{phoneNumber}</span>
        </div>
        <Phone className="h-4 w-4 text-primary" />
      </a>
    );
  }

  return (
    <a
      href={phoneLink}
      className={`fixed top-16 sm:top-20 right-4 z-[60] flex items-center gap-3 rounded-full bg-background border border-border pl-2 pr-4 py-2 shadow-lg hover:shadow-xl transition-all hover:scale-105 ${className}`}
    >
      <Image
        src="/assets/expert-patrick.jpg"
        alt="Patrick Duval"
        width={40}
        height={40}
        className="h-10 w-10 rounded-full object-cover ring-2 ring-primary/20"
      />
      <div className="hidden sm:flex flex-col">
        <span className="text-xs text-muted-foreground">Patrick Duval, expert garage</span>
        <div className="flex items-center gap-1.5">
          <Phone className="h-3.5 w-3.5 text-primary" />
          <span className="text-sm font-semibold text-primary">{phoneNumber}</span>
        </div>
      </div>
      <div className="sm:hidden flex items-center gap-1">
        <Phone className="h-4 w-4 text-primary" />
      </div>
    </a>
  );
};

export default ExpertHelpBadge;
