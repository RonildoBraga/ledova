import type { CSSProperties } from 'react';

interface SeedPhraseInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function SeedPhraseInput({ value, onChange, disabled = false }: SeedPhraseInputProps) {
  return (
    <div>
      <label className="block text-sm font-medium text-text-secondary mb-2">Seed Phrase</label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Enter your 12 or 24 word seed phrase"
        rows={3}
        disabled={disabled}
        className="w-full px-3 py-2 rounded-lg bg-surface-tertiary border border-border-subtle text-text-primary placeholder-text-muted text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand-mid/50 disabled:opacity-50"
        style={{ WebkitTextSecurity: 'disc' } as CSSProperties}
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
      />
      <p className="text-xs text-text-muted mt-1">
        Your seed phrase is used locally for signing and is never stored or transmitted.
      </p>
    </div>
  );
}
