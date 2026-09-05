import { useState, useRef, useEffect } from 'react';
import { CaretDownIcon } from '@phosphor-icons/react';
import type { CountryData } from '@ledova/shared';
import { DESIGN_TOKENS } from '@ledova/shared';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;

interface CountrySelectorProps {
  countries: CountryData[];
  selectedCountry: CountryData;
  onCountryChange: (country: CountryData) => void;
  disabled?: boolean;
}

export const CountrySelector = ({
  countries,
  selectedCountry,
  onCountryChange,
  disabled = false,
}: CountrySelectorProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [dropUp, setDropUp] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const handleCountrySelect = (country: CountryData) => {
    onCountryChange(country);
    setIsOpen(false);
  };

  const handleToggleDropdown = () => {
    if (!isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom;
      const spaceAbove = rect.top;
      const dropdownHeight = 192;

      setDropUp(spaceBelow < dropdownHeight && spaceAbove > dropdownHeight);
    }
    setIsOpen(!isOpen);
  };

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [isOpen]);

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={handleToggleDropdown}
        disabled={disabled}
        className="flex items-center gap-1 pl-10 pr-2 py-3 bg-surface-tertiary border border-border border-r-0 rounded-l-lg hover:bg-surface-raised focus:outline-none transition-colors disabled:opacity-50 disabled:cursor-not-allowed h-12"
      >
        <span className="text-lg">{selectedCountry.flag}</span>
        <span className="text-text-primary">{selectedCountry.phoneCode}</span>
        <CaretDownIcon
          size={ICON_SM}
          className={`text-text-muted transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />

          <div
            className={`absolute left-0 z-50 bg-surface-raised border border-border rounded-lg shadow-xl max-h-48 overflow-y-auto min-w-72 ${
              dropUp ? 'bottom-full mb-1' : 'top-full mt-1'
            }`}
          >
            {countries.map((country) => (
              <button
                key={country.code}
                type="button"
                onClick={() => handleCountrySelect(country)}
                className={`w-full flex items-center space-x-2 px-3 py-1.5 text-left hover:bg-surface-tertiary transition-colors ${
                  selectedCountry.code === country.code ? 'bg-surface-tertiary text-text-primary' : 'text-text-body'
                }`}
              >
                <span className="text-base">{country.flag}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{country.name}</div>
                </div>
                <div className="text-xs text-text-muted">{country.phoneCode}</div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
};
