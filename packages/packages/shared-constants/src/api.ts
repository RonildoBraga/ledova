export const API_CONFIG = {
  DEFAULT_TIMEOUT: 30000,
  DEFAULT_RETRY_ATTEMPTS: 3,
  DEFAULT_RETRY_DELAY: 1000,
} as const;

export const CACHE_TIMING = {
  VERY_SHORT_STALE_TIME: 30 * 1000,
  SHORT_STALE_TIME: 2 * 60 * 1000,
  DEFAULT_STALE_TIME: 5 * 60 * 1000,
  LONG_STALE_TIME: 10 * 60 * 1000,
  VERY_LONG_STALE_TIME: 30 * 60 * 1000,
  EXTRA_LONG_STALE_TIME: 24 * 60 * 60 * 1000,
  SIGNED_URL_REFETCH_INTERVAL: 4 * 60 * 1000,
  DEFAULT_GC_TIME: 2 * 60 * 1000,
  MEDIUM_GC_TIME: 5 * 60 * 1000,
  LONG_GC_TIME: 10 * 60 * 1000,
  VERY_LONG_GC_TIME: 30 * 60 * 1000,
  EXTRA_LONG_GC_TIME: 24 * 60 * 60 * 1000,
} as const;

export const USER_ACCOUNT_ENDPOINTS = {
  BASE: '/api/user-accounts/',
  DETAIL: (uuid: string) => `/api/user-accounts/${uuid}/` as const,
} as const;
export const AUTH_ENDPOINTS = {
  SIGNIN: '/api/signin/',
  SIGNOUT: '/api/signout/',
  SIGNUP: '/api/signup/',
  CHANGE_PASSWORD: '/api/change-password/',
  EMAIL_VERIFICATION: '/api/email-verification/',
  RESEND_VERIFICATION: '/api/resend-verification/',
  TOKEN_REFRESH: '/api/token/refresh/',
  VERIFY: '/api/auth/verify/',
} as const;
export const COUNTRY_ENDPOINTS = {
  BASE: '/api/countries/',
  DETAIL: (uuid: string) => `/api/countries/${uuid}/` as const,
} as const;
export const ASSET_ENDPOINTS = {
  BASE: '/api/assets/',
  DETAIL: (uuid: string) => `/api/assets/${uuid}/` as const,
  EXCHANGE_RATES: '/api/assets/exchange-rates/',
} as const;
export const PORTFOLIO_ENDPOINTS = {
  BASE: '/api/portfolios/',
  DETAIL: (uuid: string) => `/api/portfolios/${uuid}/` as const,
} as const;
export const USER_PROFILE_ENDPOINTS = {
  BASE: '/api/user-profiles/',
  DETAIL: (uuid: string) => `/api/user-profiles/${uuid}/` as const,
  DELETE_ACCOUNT: '/api/user-profiles/delete-account/',
  EXPORT_DATA: '/api/user-profiles/export-data/',
} as const;
export const FINANCIAL_PROFILE_ENDPOINTS = {
  BASE: '/api/financial-profiles/',
  DETAIL: (uuid: string) => `/api/financial-profiles/${uuid}/` as const,
} as const;
export const USER_PREFERENCES_ENDPOINTS = { BASE: '/api/user-preferences/' } as const;
export const IDENTITY_VERIFICATION_ENDPOINTS = {
  TOKEN: '/api/users/identity-verification/token/',
  STATUS: '/api/users/identity-verification/status/',
} as const;
export const FAVOURITE_ASSET_ENDPOINTS = {
  BASE: '/api/favourite-assets/',
  DETAIL: (uuid: string) => `/api/favourite-assets/${uuid}/` as const,
} as const;

export const DEVICE_TOKEN_ENDPOINTS = {
  BASE: '/api/device-tokens/',
  REGISTER: '/api/device-tokens/register/',
  UNREGISTER: '/api/device-tokens/unregister/',
} as const;

export const NOTIFICATION_PREFERENCES_ENDPOINTS = {
  BASE: '/api/notification-preferences/',
} as const;

export const NOTIFICATION_ENDPOINTS = {
  BASE: '/api/notifications/',
  DETAIL: (uuid: string) => `/api/notifications/${uuid}/` as const,
  UNREAD_COUNT: '/api/notifications/unread-count/',
  MARK_ALL_READ: '/api/notifications/mark-all-read/',
} as const;

export const FEATURE_FLAG_ENDPOINTS = {
  BASE: '/api/feature-flags/',
} as const;

export const COMPANY_ENDPOINTS = {
  BASE: '/api/v1/companies/',
  DETAIL: (uuid: string) => `/api/v1/companies/${uuid}/` as const,
  STATS: (uuid: string) => `/api/v1/companies/${uuid}/stats/` as const,
  DOCUMENTS: (uuid: string) => `/api/v1/companies/${uuid}/documents/` as const,
  DOCUMENT_DETAIL: (companyUuid: string, documentUuid: string) =>
    `/api/v1/companies/${companyUuid}/documents/${documentUuid}/` as const,
  APPLICATION_STATUS: (uuid: string) => `/api/v1/companies/${uuid}/application-status/` as const,
  SUBMIT: (uuid: string) => `/api/v1/companies/${uuid}/submit/` as const,
  RESUBMIT: (uuid: string) => `/api/v1/companies/${uuid}/resubmit/` as const,
  WITHDRAW: (uuid: string) => `/api/v1/companies/${uuid}/withdraw/` as const,
} as const;

export const COMPANY_TOKEN_ENDPOINTS = {
  BASE: '/api/v1/tokens/',
  DETAIL: (uuid: string) => `/api/v1/tokens/${uuid}/` as const,
  DEPLOY: (uuid: string) => `/api/v1/tokens/${uuid}/deploy/` as const,
  PAUSE: (uuid: string) => `/api/v1/tokens/${uuid}/pause/` as const,
  UNPAUSE: (uuid: string) => `/api/v1/tokens/${uuid}/unpause/` as const,
  HOLDERS: (uuid: string) => `/api/v1/tokens/${uuid}/holders/` as const,
  ISSUANCES: (uuid: string) => `/api/v1/tokens/${uuid}/issuances/` as const,
  ISSUE: (uuid: string) => `/api/v1/tokens/${uuid}/issue/` as const,
  CAPITAL_INCREASES: '/api/v1/tokens/capital-increases/',
  CAPITAL_INCREASE_DETAIL: (uuid: string) => `/api/v1/tokens/capital-increases/${uuid}/` as const,
  CAPITAL_INCREASE_SUBMIT: (uuid: string) => `/api/v1/tokens/capital-increases/${uuid}/submit/` as const,
} as const;
