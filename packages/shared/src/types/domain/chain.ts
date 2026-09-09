export type WalletPreviewChain = 'ethereum' | 'base' | 'bitcoin';

export interface BatchBalanceResponse {
  userAccount: string;
  chain: WalletPreviewChain;
  balances: Record<string, string | null>;
  errors?: string[];
}
