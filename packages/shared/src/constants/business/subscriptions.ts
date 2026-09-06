export type SubscriptionStatus =
  'draft' | 'submitted' | 'accepted' | 'awaiting_payment' | 'paid' | 'allotted' | 'rejected' | 'withdrawn' | 'refunded';

export type SettlementRail = 'bank_transfer' | 'stablecoin';

export const SUBSCRIPTION_ENDPOINTS = {
  BASE: '/api/v1/subscriptions/',
  DETAIL: (uuid: string) => `/api/v1/subscriptions/${uuid}/` as const,
  SUBMIT: (uuid: string) => `/api/v1/subscriptions/${uuid}/submit/` as const,
  WITHDRAW: (uuid: string) => `/api/v1/subscriptions/${uuid}/withdraw/` as const,
} as const;

export const SUBSCRIPTION_STATUS_LABELS: Record<SubscriptionStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  accepted: 'Accepted',
  awaiting_payment: 'Awaiting payment',
  paid: 'Paid',
  allotted: 'Allotted',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
  refunded: 'Refunded',
};

export const SUBSCRIPTION_WITHDRAWABLE_STATUSES: SubscriptionStatus[] = [
  'draft',
  'submitted',
  'accepted',
  'awaiting_payment',
];

export const SUBSCRIPTION_SUBMITTABLE_STATUSES: SubscriptionStatus[] = ['draft'];

export const SUBSCRIPTION_COPY = {
  LIST_TITLE: 'My Subscriptions',
  EMPTY_TITLE: 'You have not subscribed to anything yet',
  EMPTY_BODY:
    'Open a company in the directory and, while its offering is open, commit to a number of shares. It stays a ' +
    'draft until you submit it, and nothing is payable until the operator accepts it and issues your reference.',
  DRAFT_HELP:
    'A draft is not an application. Submitting it re-checks your investor classification and sends it to the ' +
    'operator, who accepts it and issues the exact amount and reference to pay.',
  AWAITING_PAYMENT_HELP:
    'Pay the exact amount and quote the reference exactly. The operator matches the payment by that reference, ' +
    'and shares are allotted only once the money has arrived.',
  PAID_HELP:
    'The operator has confirmed your payment. Your shares are allotted on chain shortly afterwards and then ' +
    'appear in your portfolio.',
  ALLOTTED_HELP: 'Your shares have been issued on chain. They appear in your portfolio alongside your other holdings.',
  MONEY_IN_HELP: 'A subscription with money recorded against it cannot be withdrawn. Ask the operator for a refund.',
  NO_WALLET_TITLE: 'Add a verified Base wallet first',
  NO_WALLET_BODY:
    'Shares are issued to a wallet you control, so you need a verified wallet on Base before you can subscribe. ' +
    'Add one from the Wallets page and verify it by signing the challenge.',
  SUBSCRIBE_TITLE: 'Subscribe To This Offering',
  SUBSCRIBE_INTRO:
    'Choose how many whole shares you want. The price is fixed at the offering price and frozen onto your ' +
    'subscription, so a later price change cannot move it.',
} as const;
