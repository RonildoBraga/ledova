import { SwapSettlementError } from './swap-settlement-error';
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';
import type {
  ApprovalTransaction,
  SettlementSwapOrder,
  SwapSettlementApprovalConfirmed,
  SwapSettlementApprovalData,
  SwapSettlementApprovalStatus,
  SwapSettlementApprovalUnconfirmed,
  SwapSettlementCrypto,
  SwapSettlementResponse,
  SwapSettlementSelection,
  SwapSettlementSignature,
  SwapSettlementTypedData,
} from '../types';
import {
  broadcastSwapSettlementApproval,
  getSwapSettlementApprovalData,
  getSwapSettlementApprovalStatus,
  getSwapSettlementContext,
  submitSwapSettlementSignature,
} from '../services/swap-settlement';
import { apiErrorSentence } from './errors';
import type { OrderSubmissionOwner } from './order-submission-storage';
import type { SavedSwapSettlement, SwapSettlementStore } from './swap-settlement-storage';
import {
  swapSettlementAdmitted,
  swapSettlementIdentity,
  swapSettlementRole,
  validateSettlementSwapOrder,
  validateSwapSettlementApprovalData,
  validateSwapSettlementApprovalResult,
  validateSwapSettlementApprovalStatus,
  validateSwapSettlementLookup,
  validateSwapSettlementResponse,
  validateSwapSettlementSignedApproval,
} from './swap-settlement-validation';

export type SwapSettlementPhase =
  | 'loading'
  | 'ready'
  | 'signing'
  | 'submitting'
  | 'approval-loading'
  | 'approval-ready'
  | 'approval-signing'
  | 'approval-submitting'
  | 'error';

export interface SwapSettlementState {
  attempt: number;
  phase: SwapSettlementPhase;
  response: SwapSettlementResponse | null;
  approvalStatus: SwapSettlementApprovalStatus | null;
  approvalData: SwapSettlementApprovalData | null;
  approvalResult: SwapSettlementApprovalConfirmed | SwapSettlementApprovalUnconfirmed | null;
  unconfirmedApprovalHashes: readonly string[];
  error: string | null;
  notice: string | null;
}

export interface SwapSettlementDependencies {
  apiClient: AxiosInstance;
  store: SwapSettlementStore;
  crypto: SwapSettlementCrypto;
  isCurrent: () => boolean;
  requestConfig?: AxiosRequestConfig;
  onRecordsChanged: () => void;
  onUpdated: (order: SettlementSwapOrder) => void;
}

function frozen<T>(value: T): T {
  if (value && typeof value === 'object') {
    for (const item of Object.values(value)) frozen(item);
    Object.freeze(value);
  }
  return value;
}

function copied<T>(value: T): T {
  return frozen(JSON.parse(JSON.stringify(value)) as T);
}

export class SwapSettlement {
  readonly owner: OrderSubmissionOwner;
  readonly selection: SwapSettlementSelection;
  private state: SwapSettlementState = {
    attempt: 0,
    phase: 'loading',
    response: null,
    approvalStatus: null,
    approvalData: null,
    approvalResult: null,
    unconfirmedApprovalHashes: [],
    error: null,
    notice: null,
  };
  private listeners = new Set<() => void>();
  private generation = 0;
  private retired = false;
  private busy = false;
  private known: SettlementSwapOrder | null = null;
  private signatureRecoveryRequired = false;

  constructor(
    owner: OrderSubmissionOwner,
    selection: SwapSettlementSelection,
    private dependencies: SwapSettlementDependencies,
  ) {
    validateSwapSettlementLookup(selection);
    if (owner.ownerAccountUuid !== selection.ownerAccountUuid)
      throw new SwapSettlementError('Choose a swap belonging to the current account.');
    this.owner = Object.freeze({ ...owner });
    this.selection = Object.freeze({ ...selection });
  }

  getSnapshot = (): SwapSettlementState => this.state;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  isCurrent = (): boolean => {
    if (!this.retired && !this.dependencies.isCurrent()) this.close();
    return !this.retired;
  };
  close = (): void => {
    this.retired = true;
    this.generation++;
  };
  private current(generation: number): boolean {
    return this.isCurrent() && generation === this.generation;
  }
  private publish(next: Partial<SwapSettlementState>): void {
    this.state = Object.freeze({ ...this.state, ...next });
    for (const listener of [...this.listeners]) {
      try {
        listener();
      } catch {
        console.warn('Settlement view update did not complete.');
      }
    }
  }
  private config(generation: number, newWork = false): AxiosRequestConfig {
    return {
      ...this.dependencies.requestConfig,
      ledovaSubmissionGuard: () => {
        this.dependencies.requestConfig?.ledovaSubmissionGuard?.();
        if (!this.current(generation)) throw new SwapSettlementError('This settlement view is no longer active.');
        if (newWork && (!this.state.response || !swapSettlementAdmitted(this.state.response)))
          throw new SwapSettlementError('Refresh the original settlement before continuing.');
      },
    };
  }
  private async run(phase: SwapSettlementPhase, operation: (generation: number) => Promise<void>): Promise<void> {
    if (!this.isCurrent() || this.busy) return;
    this.busy = true;
    const generation = ++this.generation;
    this.publish({ attempt: generation, phase, error: null, notice: null });
    try {
      if (this.current(generation)) await operation(generation);
    } catch (error) {
      if (this.current(generation))
        this.publish({
          phase: 'error',
          approvalData: null,
          error: apiErrorSentence(
            error,
            error instanceof SwapSettlementError
              ? error.message
              : 'The original settlement result is unavailable. Check its saved status.',
          ),
        });
    } finally {
      if (generation === this.generation) this.busy = false;
    }
  }
  private requireAdmission(generation: number): SwapSettlementResponse {
    this.config(generation, true).ledovaSubmissionGuard!();
    return this.state.response!;
  }
  private sameRecord(record: SavedSwapSettlement): boolean {
    const response = this.state.response;
    return (
      !!response &&
      record.userUuid === this.owner.userUuid &&
      record.ownerAccountUuid === response.ownerAccountUuid &&
      record.orderUuid === response.orderUuid &&
      record.swapUuid === response.swapUuid &&
      record.walletUuid === response.walletUuid &&
      record.settlementDigest === response.settlementDigest
    );
  }
  private async clear(record: SavedSwapSettlement, generation: number): Promise<void> {
    if (!this.current(generation)) return;
    try {
      await this.dependencies.store.remove(record);
      if (this.current(generation) && record.kind === 'approval')
        this.publish({
          unconfirmedApprovalHashes: this.state.unconfirmedApprovalHashes.filter((hash) => hash !== record.txHash),
        });
    } catch {
      if (this.current(generation))
        this.publish({
          notice: 'The result is recorded. Its saved reminder could not be cleared; checking it again is safe.',
        });
    }
    if (this.current(generation)) this.dependencies.onRecordsChanged();
  }
  private async clearObservedSignatures(generation: number): Promise<void> {
    const records = await this.dependencies.store.list(this.owner);
    if (!this.current(generation)) return;
    this.publish({
      unconfirmedApprovalHashes: records
        .filter((record) => record.kind === 'approval' && this.sameRecord(record))
        .map((record) => (record as Extract<SavedSwapSettlement, { kind: 'approval' }>).txHash),
    });
    for (const record of records) {
      if (!this.current(generation)) return;
      if (record.kind !== 'signature' || !this.sameRecord(record)) continue;
      const role = swapSettlementRole(this.state.response!, record.signerAddress);
      if (
        role === 'seller'
          ? this.state.response!.swapOrder.sellerHasSigned
          : this.state.response!.swapOrder.buyerHasSigned
      )
        await this.clear(record, generation);
    }
  }
  private async read(generation: number): Promise<void> {
    const lookup = this.known ? { ...this.selection, settlementDigest: this.known.settlementDigest } : this.selection;
    const result = await getSwapSettlementContext(this.dependencies.apiClient, lookup, this.config(generation));
    if (!this.current(generation)) return;
    const response = copied(result.data);
    if (result.status !== 200)
      throw new SwapSettlementError('The settlement response did not establish the original context.');
    await validateSwapSettlementResponse(response, this.selection, this.dependencies.crypto, this.known);
    if (!this.current(generation)) return;
    this.known = response.swapOrder;
    this.signatureRecoveryRequired = false;
    this.publish({ phase: 'ready', response, approvalStatus: null, approvalData: null });
    if (!this.current(generation)) return;
    await this.clearObservedSignatures(generation);
  }
  load = (): Promise<void> => this.run('loading', (generation) => this.read(generation));
  recover = (): Promise<void> => this.load();

  refreshApprovalStatus = (): Promise<void> =>
    this.run('approval-loading', async (generation) => {
      const response = this.requireAdmission(generation);
      const result = await getSwapSettlementApprovalStatus(
        this.dependencies.apiClient,
        response,
        this.config(generation, true),
      );
      if (!this.current(generation)) return;
      const status = copied(result.data);
      if (result.status !== 200) throw new SwapSettlementError('The allowance response is unavailable.');
      validateSwapSettlementApprovalStatus(status, response);
      this.requireAdmission(generation);
      this.publish({ phase: 'ready', approvalStatus: status, approvalData: null });
    });

  prepareApproval = (): Promise<void> =>
    this.run('approval-loading', async (generation) => {
      const response = this.requireAdmission(generation);
      const result = await getSwapSettlementApprovalData(
        this.dependencies.apiClient,
        response,
        this.config(generation, true),
      );
      if (!this.current(generation)) return;
      const data = copied(result.data);
      if (result.status !== 200) throw new SwapSettlementError('The approval request is unavailable.');
      validateSwapSettlementApprovalData(data, response);
      const records = await this.dependencies.store.list(this.owner);
      if (!this.current(generation)) return;
      this.requireAdmission(generation);
      if (data.needsApproval && records.some((record) => record.kind === 'approval' && this.sameRecord(record)))
        throw new SwapSettlementError(
          'An earlier approval remains unconfirmed. Check its original transaction before sending another.',
        );
      this.publish({ phase: data.needsApproval ? 'approval-ready' : 'ready', approvalData: data });
    });

  private async sendSignature(input: SwapSettlementSignature, generation: number): Promise<void> {
    if (this.signatureRecoveryRequired)
      throw new SwapSettlementError('Check the saved settlement status before signing again.');
    const value = copied(input);
    const response = this.requireAdmission(generation);
    if (!value || !/^0x[0-9a-f]{130}$/i.test(value.signature))
      throw new SwapSettlementError('The settlement signature is invalid.');
    const role = swapSettlementRole(response, value.signerAddress);
    const recovered = await this.dependencies.crypto.recoverSigner(response.typedData, value.signature);
    if (!this.current(generation)) return;
    if (typeof recovered !== 'string' || recovered.toLowerCase() !== value.signerAddress.toLowerCase())
      throw new SwapSettlementError('The signature did not match the reviewed settlement and signer.');
    this.requireAdmission(generation);
    const record: SavedSwapSettlement = {
      version: 1,
      ...this.owner,
      ...swapSettlementIdentity(response),
      kind: 'signature',
      signerAddress: value.signerAddress.toLowerCase(),
    };
    await this.dependencies.store.save(record);
    if (!this.current(generation)) return;
    this.dependencies.onRecordsChanged();
    this.requireAdmission(generation);
    this.publish({ phase: 'submitting' });
    this.config(generation, true).ledovaSubmissionGuard!();
    this.signatureRecoveryRequired = true;
    const result = await submitSwapSettlementSignature(
      this.dependencies.apiClient,
      response,
      value,
      this.config(generation, true),
    );
    if (!this.current(generation)) return;
    const order = copied(result.data);
    if (result.status !== 200)
      throw new SwapSettlementError('The signature response did not establish a recorded result.');
    await validateSettlementSwapOrder(order, response, this.dependencies.crypto, this.known);
    if (!this.current(generation)) return;
    if (!(role === 'seller' ? order.sellerHasSigned : order.buyerHasSigned))
      throw new SwapSettlementError('The signature was not recorded in the returned settlement.');
    this.known = order;
    this.signatureRecoveryRequired = false;
    this.publish({
      response: frozen({
        ...response,
        swapOrder: order,
        hasSigned: response.userRole === 'seller' ? order.sellerHasSigned : order.buyerHasSigned,
        canSign: false,
        admissionRefusal: 'swap_status_refresh_required',
      }),
    });
    if (!this.current(generation)) return;
    this.dependencies.onUpdated(order);
    await this.clear(record, generation);
    if (this.current(generation)) await this.read(generation);
  }
  sign = (
    signer: (typedData: SwapSettlementTypedData, isCurrent: () => boolean) => Promise<SwapSettlementSignature | null>,
  ): Promise<void> =>
    this.state.phase !== 'ready'
      ? Promise.resolve()
      : this.run('signing', async (generation) => {
          if (this.signatureRecoveryRequired)
            throw new SwapSettlementError('Check the saved settlement status before signing again.');
          const response = this.requireAdmission(generation);
          const signature = await signer(
            response.typedData,
            () => this.current(generation) && swapSettlementAdmitted(response),
          );
          if (!this.current(generation)) return;
          if (signature) await this.sendSignature(signature, generation);
          else this.publish({ phase: 'ready' });
        });
  submitSignature = (signature: string, signerAddress: string): Promise<void> =>
    this.state.phase !== 'ready'
      ? Promise.resolve()
      : this.run('submitting', (generation) => this.sendSignature({ signature, signerAddress }, generation));

  private async sendApproval(raw: string, generation: number): Promise<void> {
    const response = this.requireAdmission(generation);
    const prepared = this.state.approvalData;
    if (!prepared?.needsApproval || !/^(0x)?(?:[0-9a-f]{2})+$/i.test(raw) || raw.length > 32768)
      throw new SwapSettlementError('Prepare and review this approval before signing.');
    const inspected = copied(await this.dependencies.crypto.inspectSignedApproval(raw));
    if (!this.current(generation)) return;
    validateSwapSettlementSignedApproval(inspected, prepared.transaction, response);
    const records = await this.dependencies.store.list(this.owner);
    if (!this.current(generation)) return;
    if (records.some((record) => record.kind === 'approval' && this.sameRecord(record)))
      throw new SwapSettlementError(
        'An earlier approval remains unconfirmed. Check its original transaction before sending another.',
      );
    const record: SavedSwapSettlement = {
      version: 1,
      ...this.owner,
      ...swapSettlementIdentity(response),
      kind: 'approval',
      txHash: inspected.txHash.toLowerCase(),
    };
    await this.dependencies.store.save(record);
    if (!this.current(generation)) return;
    this.dependencies.onRecordsChanged();
    this.requireAdmission(generation);
    this.publish({
      phase: 'approval-submitting',
      unconfirmedApprovalHashes: [...new Set([...this.state.unconfirmedApprovalHashes, record.txHash])],
    });
    this.config(generation, true).ledovaSubmissionGuard!();
    let result: AxiosResponse<SwapSettlementApprovalConfirmed | SwapSettlementApprovalUnconfirmed>;
    try {
      result = await broadcastSwapSettlementApproval(
        this.dependencies.apiClient,
        response,
        raw,
        this.config(generation, true),
      );
    } catch (error) {
      const observed = (error as { response?: AxiosResponse<SwapSettlementApprovalUnconfirmed> })?.response;
      if (observed?.status !== 503) throw error;
      result = observed;
    }
    if (!this.current(generation)) return;
    const outcome = copied(result.data);
    validateSwapSettlementApprovalResult(outcome, result.status, response, record.txHash);
    this.publish({
      phase: 'ready',
      approvalData: null,
      approvalResult: outcome,
      notice:
        result.status === 503
          ? 'Approval outcome remains unconfirmed. Check the original transaction before continuing.'
          : null,
    });
    if (!this.current(generation)) return;
    if (result.status === 200) {
      await this.clear(record, generation);
      if (this.current(generation)) this.dependencies.onUpdated(response.swapOrder);
    }
  }
  signApproval = (
    signer: (transaction: ApprovalTransaction, isCurrent: () => boolean) => Promise<string | null>,
  ): Promise<void> =>
    this.run('approval-signing', async (generation) => {
      const response = this.requireAdmission(generation);
      const prepared = this.state.approvalData;
      if (!prepared?.needsApproval) throw new SwapSettlementError('Prepare and review this approval before signing.');
      const raw = await signer(
        prepared.transaction,
        () => this.current(generation) && swapSettlementAdmitted(response),
      );
      if (!this.current(generation)) return;
      if (raw) await this.sendApproval(raw, generation);
      else this.publish({ phase: 'approval-ready' });
    });
  broadcastApproval = (raw: string): Promise<void> =>
    this.run('approval-submitting', (generation) => this.sendApproval(raw, generation));
}
