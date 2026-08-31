export interface FormErrors {
  [key: string]: string[];
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface BaseOperationResponse {
  uuid: string;
  message?: string;
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

export interface SearchParams {
  search?: string;
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

export interface AccountExportData {
  exportedAt: string;
  user: {
    email: string;
    dateJoined: string | null;
    isEmailVerified: boolean;
  };
  profile: {
    firstName: string;
    middleName: string;
    lastName: string;
    dateOfBirth: string | null;
    phoneNumber: string;
    citizenshipCountry: string | null;
    createdAt: string | null;
  } | null;
  preferences: {
    selectedPortfolio: string | null;
    selectedAccount: string | null;
  } | null;
  financialProfile: {
    employmentStatus: string;
    annualIncome: string | null;
    sourceOfFunds: string;
    investmentExperience: string;
    riskTolerance: string;
    investmentObjective: string;
  } | null;
  accounts: Array<{
    uuid: string;
    accountNumber: string;
    accountType: string;
    createdAt: string | null;
  }>;
  wallets: Array<{
    uuid: string;
    name: string;
    chain: string;
    address: string;
    balance: string;
    isVerified: boolean;
    createdAt: string | null;
  }>;
  transactions: Array<{
    uuid: string;
    txHash: string;
    type: string;
    status: string;
    amount: string;
    fee: string;
    fromAddress: string;
    toAddress: string;
    createdAt: string | null;
  }>;
  portfolios: Array<{
    uuid: string;
    name: string;
    description: string;
    createdAt: string | null;
  }>;
}
