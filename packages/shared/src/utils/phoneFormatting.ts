interface CountryInfo {
  phoneCode: string;
  code?: string;
}

function australianNational(cleaned: string): string {
  return `${cleaned.slice(0, 4)} ${cleaned.slice(4, 7)} ${cleaned.slice(7)}`;
}

function australianInternational(cleaned: string): string {
  return `${cleaned.slice(0, 3)} ${cleaned.slice(3, 6)} ${cleaned.slice(6)}`;
}

export function formatPhoneForDisplay(phoneNumber: string, country?: CountryInfo): string {
  if (!phoneNumber) return '';
  const cleaned = phoneNumber.replace(/\D/g, '');
  const phoneCode = country?.phoneCode?.replace('+', '') || '61';

  if (phoneCode === '61') {
    if (/^(?:0\d{9}|1[38]00\d{6})$/.test(cleaned)) return australianNational(cleaned);
    if (/^4\d{8}$/.test(cleaned)) return australianInternational(cleaned);
    return phoneNumber.trim();
  }
  if (phoneCode === '1' && cleaned.length >= 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6, 10)}`;
  }
  return phoneNumber.trim();
}

export function cleanPhoneNumber(phoneNumber: string): string {
  return phoneNumber.replace(/\D/g, '');
}
