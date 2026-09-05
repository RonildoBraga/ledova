export interface ValidationResult {
  isValid: boolean;
  message?: string;
}

export interface FieldValidation extends ValidationResult {
  isEmpty: boolean;
}

export interface FormValidation {
  isFormValid: boolean;
  fields?: Record<string, ValidationResult>;
}
