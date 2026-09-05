export interface FormErrors {
  [key: string]: string[];
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface PaginationParams {
  page?: number;
  page_size?: number;
}

export interface LimitParams {
  limit?: number;
  offset?: number;
}

export interface OrderingParams {
  order_by?: string;
}

export interface DateRangeParams {
  start_date?: string;
  end_date?: string;
}

export type BaseQueryParams = PaginationParams & OrderingParams;

export type TimeSeriesQueryParams = LimitParams &
  OrderingParams &
  DateRangeParams & {
    max_points?: number;
  };

export interface UserFriendlyError extends Error {
  isUserFriendly: true;
  originalError?: unknown;
}

/** Mirrors backend `users.services.lifecycle.export_account_data`; both clients only JSON.stringify it. */
export interface AccountExportData {
  exportedAt: string;
  user: {
    email: string;
    dateJoined: string;
    isEmailVerified: boolean;
  };
  profile: {
    fullName: string | null;
    dateOfBirth: string | null;
    phoneCountryCode: string | null;
    phoneNumber: string | null;
    residentialAddress: string | null;
    citizenshipCountry: string | null;
    isIdVerified: boolean;
    createdAt: string;
  } | null;
  preferences: {
    selectedPortfolio: string | null;
    selectedAccount: string | null;
  } | null;
  financialProfile: {
    occupation: string | null;
    sourceOfFunds: string[] | null;
    sourceOfFundsOtherText: string | null;
    intendedUse: string | null;
    intendedUseOtherText: string | null;
  } | null;
  accounts: Array<{
    uuid: string;
    accountNumber: string;
    accountType: string;
    activationDate: string | null;
    createdAt: string;
  }>;
  wallets: Array<{
    uuid: string;
    name: string | null;
    chain: string;
    address: string;
    nativeBalance: string;
    marketValue: string;
    isVerified: boolean;
    createdAt: string;
  }>;
  transactions: Array<{
    uuid: string;
    txHash: string;
    chain: string;
    status: string;
    asset: string | null;
    amount: string;
    transactionFee: string | null;
    fromAddress: string;
    toAddress: string | null;
    blockTimestamp: string | null;
    createdAt: string;
  }>;
  portfolios: Array<{
    uuid: string;
    name: string;
    isActive: boolean;
    createdAt: string;
  }>;
}
