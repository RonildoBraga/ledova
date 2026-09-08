interface CountryInfo {
  phoneCode: string;
  code?: string;
}

function australianNational(cleaned: string): string {
  const digits = cleaned.slice(0, 10);
  return `${digits.slice(0, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`;
}

function australianInternational(cleaned: string): string {
  const digits = cleaned.slice(0, 9);
  return `${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6)}`;
}

export function formatPhoneForDisplay(phoneNumber: string, country?: CountryInfo): string {
  if (!phoneNumber) return '';
  const cleaned = phoneNumber.replace(/\D/g, '');
  const phoneCode = country?.phoneCode?.replace('+', '') || '61';

  if (phoneCode === '61' && cleaned.length >= 9) {
    return cleaned.startsWith('0') ? australianNational(cleaned) : australianInternational(cleaned);
  }
  if (phoneCode === '1' && cleaned.length >= 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6, 10)}`;
  }
  return phoneNumber.trim();
}

export function cleanPhoneNumber(phoneNumber: string): string {
  return phoneNumber.replace(/\D/g, '');
}
