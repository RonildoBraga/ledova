const normalizeBaseUrl = (value: string): string => value.replace(/\/$/, '');

export const MARKETING_URL = normalizeBaseUrl(process.env.EXPO_PUBLIC_MARKETING_URL || 'http://localhost:5173');
export const SUPPORT_EMAIL = process.env.EXPO_PUBLIC_SUPPORT_EMAIL || '';
export const APP_STORE_URL = process.env.EXPO_PUBLIC_APP_STORE_URL || '';

export const PUBLIC_LINKS = {
  helpCenter: `${MARKETING_URL}/help-center`,
  termsOfService: `${MARKETING_URL}/terms-of-service`,
  privacyPolicy: `${MARKETING_URL}/privacy-policy`,
} as const;
