"use client";

import { AlertTriangle } from "lucide-react";

interface WarningBannerProps {
  message: string;
}

const WarningBanner = ({ message }: WarningBannerProps) => {
  return (
    <div className="flex items-center gap-3 rounded-lg bg-warning/10 border border-warning/30 px-4 py-3">
      <AlertTriangle className="h-5 w-5 text-warning shrink-0" />
      <p className="text-sm text-warning">{message}</p>
    </div>
  );
};

export default WarningBanner;
