interface CountryInfo {
  phoneCode: string;
  code?: string;
}

export function formatPhoneForDisplay(phoneNumber: string, country?: CountryInfo): string {
  if (!phoneNumber) return '';
  const cleaned = phoneNumber.replace(/\D/g, '');
  const phoneCode = country?.phoneCode?.replace('+', '') || '61';

  if (phoneCode === '61' && cleaned.length >= 9) {
    const digits = cleaned.slice(0, 10);
    return `${digits.slice(0, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`;
  }
  if (phoneCode === '1' && cleaned.length >= 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6, 10)}`;
  }
  return phoneNumber.trim();
}

export function cleanPhoneNumber(phoneNumber: string): string {
  return phoneNumber.replace(/\D/g, '');
}
