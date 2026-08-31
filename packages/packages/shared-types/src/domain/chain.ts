export interface BatchBalanceResponse {
  balances: Record<string, string>;
  errors?: string[];
}
