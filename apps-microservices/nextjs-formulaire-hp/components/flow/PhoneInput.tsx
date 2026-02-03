'use client';

import { useState, useEffect } from 'react';
import CountryCodeSelect from './CountryCodeSelect';
import {
  validatePhoneNumber,
  formatPhoneNumber,
  sanitizePhoneInput,
  getCountryConfig,
} from '@/lib/utils/phone-validation';

interface PhoneInputProps {
  value: string;
  countryCode: string;
  onValueChange: (value: string) => void;
  onCountryCodeChange: (code: string) => void;
  error?: string;
  required?: boolean;
  disabled?: boolean;
  className?: string;
}

const PhoneInput = ({
  value,
  countryCode,
  onValueChange,
  onCountryCodeChange,
  error,
  required = false,
  disabled = false,
  className = '',
}: PhoneInputProps) => {
  const [internalError, setInternalError] = useState<string | undefined>();
  const [touched, setTouched] = useState(false);

  const config = getCountryConfig(countryCode);
  const placeholder = config?.placeholder || '123 456 789';

  // Valider le numéro quand il change ou quand le pays change
  useEffect(() => {
    if (touched && value) {
      const validation = validatePhoneNumber(value, countryCode);
      setInternalError(validation.error);
    }
  }, [value, countryCode, touched]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const sanitized = sanitizePhoneInput(e.target.value);
    const formatted = formatPhoneNumber(sanitized, countryCode);
    onValueChange(formatted);
  };

  const handleBlur = () => {
    setTouched(true);
    if (value) {
      const validation = validatePhoneNumber(value, countryCode);
      setInternalError(validation.error);
    }
  };

  const handleCountryChange = (newCode: string) => {
    onCountryCodeChange(newCode);
    // Reformater le numéro avec le nouveau pays
    if (value) {
      const cleaned = value.replace(/\D/g, '');
      const formatted = formatPhoneNumber(cleaned, newCode);
      onValueChange(formatted);
    }
  };

  const displayError = error || internalError;
  const hasError = touched && !!displayError;

  return (
    <div className={className}>
      <div className="flex gap-2">
        <CountryCodeSelect value={countryCode} onChange={handleCountryChange} />
        <div className="flex-1">
          <input
            type="tel"
            value={value}
            onChange={handleChange}
            onBlur={handleBlur}
            placeholder={placeholder}
            required={required}
            disabled={disabled}
            className={`w-full rounded-lg border px-4 py-3 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 transition-all ${
              hasError
                ? 'border-destructive focus:border-destructive focus:ring-destructive/20'
                : 'border-input focus:border-primary focus:ring-primary/20'
            } ${disabled ? 'bg-muted cursor-not-allowed' : 'bg-background'}`}
          />
        </div>
      </div>

      {/* Error message */}
      {hasError && (
        <p className="mt-1.5 text-sm text-destructive flex items-center gap-1">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="w-4 h-4"
          >
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z"
              clipRule="evenodd"
            />
          </svg>
          {displayError}
        </p>
      )}

      {/* Help text avec exemple */}
      {!hasError && config && (
        <p className="mt-1.5 text-xs text-muted-foreground">
          Exemple: {config.placeholder}
        </p>
      )}
    </div>
  );
};

export default PhoneInput;
