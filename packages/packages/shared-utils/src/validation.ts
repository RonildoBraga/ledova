import type { PasswordValidation, EmailConfirmationValidation } from '@ledova/shared-types';

export function isNumericOnly(str: string): boolean {
  return /^\d+$/.test(str);
}

export function validatePassword(password: string, minLength = 8): PasswordValidation {
  const lengthValid = password.length >= minLength;
  const notNumeric = !isNumericOnly(password);
  return { isValid: lengthValid && notNumeric, lengthValid, notNumeric };
}

export function formatVerificationToken(token: string): string {
  return token.trim().replace(/[^0-9]/g, '');
}

export function validateEmailConfirmation(token: string, exactLength = 6): EmailConfirmationValidation {
  const formattedToken = formatVerificationToken(token);
  const isValidFormat = new RegExp(`^[0-9]{${exactLength}}$`).test(formattedToken);
  return {
    isValid: formattedToken.length === exactLength && isValidFormat,
    isEmpty: formattedToken.length === 0,
    isValidFormat,
  };
}

export function isValidFullName(fullName: string, minParts = 2): boolean {
  const trimmedName = fullName.trim();
  const nameParts = trimmedName.split(/\s+/);
  return nameParts.length >= minParts && nameParts.every((part) => part.length > 0);
}

export function isValidPhoneFormat(phoneNumber: string, minLength = 8): boolean {
  const trimmedPhone = phoneNumber.trim();
  return trimmedPhone.length >= minLength && /^[+\-\s\d()]+$/.test(trimmedPhone);
}

export function formatPhoneNumber(phoneNumber: string): string {
  if (!phoneNumber) return '';
  const cleaned = phoneNumber.replace(/\D/g, '');
  if (cleaned.startsWith('61') && cleaned.length === 11) {
    const mobile = cleaned.slice(2);
    return `+61 ${mobile.slice(0, 3)} ${mobile.slice(3, 6)} ${mobile.slice(6)}`;
  }
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  return phoneNumber.trim();
}
