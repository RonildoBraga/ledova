interface ValidationResult {
  isValid: boolean;
}

function validateFullName(value: string): ValidationResult {
  if (!value) return { isValid: false };
  const trimmed = value.trim();
  return { isValid: trimmed.split(/\s+/).length >= 2 };
}

function validatePhoneNumber(value: string): ValidationResult {
  if (!value) return { isValid: false };
  const trimmed = value.trim();
  return { isValid: trimmed.length >= 8 && /^[+\-\s\d()]+$/.test(trimmed) };
}

function validateResidentialAddress(value: string): ValidationResult {
  if (!value) return { isValid: false };
  return { isValid: value.trim().length >= 10 };
}

export const validateUserProfileField = {
  fullName: validateFullName,
  phoneNumber: validatePhoneNumber,
  residentialAddress: validateResidentialAddress,
};
