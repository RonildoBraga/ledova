export type OfferingStatus = 'draft' | 'submitted' | 'under_review' | 'approved' | 'rejected' | 'closed' | 'withdrawn';

export type OfferingExemption =
  | 's708_8_minimum_amount'
  | 's708_8_net_assets'
  | 's708_8_gross_income'
  | 's708_11_professional'
  | 's761g_wholesale_client';

export const DIRECTORY_ENDPOINTS = {
  TOKENS: {
    LIST: '/api/v1/directory/tokens/',
    DETAIL: (uuid: string) => `/api/v1/directory/tokens/${uuid}/` as const,
  },
} as const;

export const OFFERING_ENDPOINTS = {
  BASE: '/api/v1/offerings/',
  DETAIL: (uuid: string) => `/api/v1/offerings/${uuid}/` as const,
  SUBMIT: (uuid: string) => `/api/v1/offerings/${uuid}/submit/` as const,
  WITHDRAW: (uuid: string) => `/api/v1/offerings/${uuid}/withdraw/` as const,
  SUBSCRIPTIONS: (uuid: string) => `/api/v1/offerings/${uuid}/subscriptions/` as const,
} as const;

export const OFFERING_EXEMPTION_LABELS: Record<OfferingExemption, string> = {
  s708_8_minimum_amount: 'Minimum amount of AUD 500,000 (s708(8)(a))',
  s708_8_net_assets: 'Net assets certified by a qualified accountant (s708(8)(c))',
  s708_8_gross_income: 'Gross income certified by a qualified accountant (s708(8)(c))',
  s708_11_professional: 'Professional investor (s708(11))',
  s761g_wholesale_client: 'Wholesale client (s761G)',
};

export const OFFERING_EDITABLE_STATUSES: OfferingStatus[] = ['draft'];
export const OFFERING_WITHDRAWABLE_STATUSES: OfferingStatus[] = ['draft', 'submitted', 'under_review'];

export const DIRECTORY_COPY = {
  EMPTY_TITLE: 'No companies are listed yet',
  EMPTY_BODY:
    'A company appears here once its owner has opted in and one of its share classes is deployed on chain. ' +
    'Both are needed, so the directory can be empty while an issuer has already opted in and is waiting to ' +
    'deploy. Nothing is hidden from you. Check back, or ask the operator when the first share class is ' +
    'expected on chain.',
  INELIGIBLE_TITLE: 'Verify your investor status to see the directory',
  INELIGIBLE_BODY:
    'Offers on this platform are made only to wholesale and sophisticated investors. Submit a classification ' +
    'with evidence and the operator will verify it, usually within a few business days.',
  MARKET_INELIGIBLE_BODY:
    'The market list is limited to verified wholesale and sophisticated investors. Once your classification is ' +
    'verified, every deployed share class appears here, whether or not its issuer is listed in the directory.',
  MARKET_EMPTY_TITLE: 'No share classes are trading yet',
  MARKET_EMPTY_BODY:
    'No company has deployed a share class on this platform yet. The market lists every deployed share class, ' +
    'so this is empty only because none exists.',
} as const;
