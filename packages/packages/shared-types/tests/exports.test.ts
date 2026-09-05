import type {
  AccountExportData,
  AssetFilters,
  AuthVerificationResponse,
  HoldingsQueryParams,
  Portfolio,
  PortfolioSnapshotQueryParams,
  PortfolioSnapshotReason,
  PrepareBitcoinTransferRequest,
  PrepareBitcoinTransferResponse,
  PrepareTransferRequest,
  UpdateUserProfile,
  UserProfile,
} from '../src';

type Has<T, K extends PropertyKey> = K extends keyof T ? true : false;

describe('shared-types exports', () => {
  it('should export type definitions module', () => {
    const typeExports = require('../src/index');
    expect(typeExports).toBeDefined();
  });

  it('exposes the public compile-time type surface', () => {
    const filters: AssetFilters = { search: 'synthetic', chain: 'ethereum' };
    const profileEmailIsResponseOnly: 'email' extends keyof UpdateUserProfile ? false : true = true;
    expect(filters).toEqual({ search: 'synthetic', chain: 'ethereum' });
    expect(profileEmailIsResponseOnly).toBe(true);
  });

  it('keeps UserProfile aligned with UserProfileSerializer.Meta.fields', () => {
    const emitted: Has<UserProfile, 'kycProvider' | 'verificationStatus' | 'reviewResult' | 'residenceCountryName'> =
      true;
    const dropped: Has<
      UserProfile,
      'preScreeningCompletedAt' | 'sumsubReviewResult' | 'sumsubVerifiedAt' | 'createdAt'
    > = false;
    const kycIsResponseOnly: Has<UpdateUserProfile, 'kycProvider' | 'verificationStatus' | 'isIdVerified'> = false;
    const preScreeningIsWritable: Has<UpdateUserProfile, 'confirmedOver18' | 'citizenshipCountry'> = true;
    expect([emitted, dropped, kycIsResponseOnly, preScreeningIsWritable]).toEqual([true, false, false, true]);
  });

  it('keeps AccountExportData aligned with export_account_data', () => {
    const profileKeys: Has<NonNullable<AccountExportData['profile']>, 'fullName' | 'isIdVerified'> = true;
    const walletKeys: Has<AccountExportData['wallets'][number], 'nativeBalance' | 'marketValue'> = true;
    const legacyWalletKey: Has<AccountExportData['wallets'][number], 'balance'> = false;
    expect([profileKeys, walletKeys, legacyWalletKey]).toEqual([true, true, false]);
  });

  it('keeps the EVM and Bitcoin prepare-transfer contracts apart', () => {
    const evmHasNoBtcAmount: Has<PrepareTransferRequest, 'amountBtc'> = false;
    const btcRequest: PrepareBitcoinTransferRequest = { toAddress: `tb1q${'a'.repeat(38)}`, amountBtc: '0.001' };
    const btcResponseKeys: Has<
      PrepareBitcoinTransferResponse,
      'amountBtc' | 'feeBtc' | 'totalCostBtc' | 'feePerByte' | 'estimatedTxSize'
    > = true;
    expect([evmHasNoBtcAmount, btcResponseKeys]).toEqual([false, true]);
    expect(btcRequest.amountBtc).toBe('0.001');
  });

  it('drops the query params and response fields the backend no longer reads or emits', () => {
    const minValue: Has<HoldingsQueryParams, 'min_value'> = false;
    const reason: Has<AuthVerificationResponse, 'reason'> = false;
    const portfolioTotal: Has<Portfolio, 'totalValue' | 'template'> = false;
    const snapshotReasonParam: Has<PortfolioSnapshotQueryParams, 'snapshot_reason'> = false;
    const onlyDaily: PortfolioSnapshotReason = 'DAILY';
    expect([minValue, reason, portfolioTotal, snapshotReasonParam]).toEqual([false, false, false, false]);
    expect(onlyDaily).toBe('DAILY');
  });
});
