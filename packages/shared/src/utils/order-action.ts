import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';
import type {
  OrderActionChallenge,
  OrderActionContext,
  OrderActionPurpose,
  OrderActionSnapshot,
  OrderActionValues,
} from '../types';
import {
  cancelOrder,
  getOrderAction,
  getOrderActionContext,
  getOrderCancelMessage,
  getOrderModificationMessage,
  modifyOrder,
} from '../services/trading';
import { apiErrorSentence } from './errors';
import type { OrderSubmissionOwner } from './order-submission-storage';
import type { OrderActionStore, SavedOrderAction } from './order-action-storage';
import {
  canonicalOrderActionValues,
  validateOrderActionContext,
  validateOrderActionIssuance,
  validateOrderActionSnapshot,
} from './order-action-validation';

export type OrderActionPhase =
  'loading' | 'editing' | 'preparing' | 'ready' | 'signing' | 'submitting' | 'applied' | 'refused' | 'error';

export interface OrderActionState {
  attempt: number;
  phase: OrderActionPhase;
  context: OrderActionContext | null;
  values: OrderActionValues | null;
  snapshot: OrderActionSnapshot | null;
  challenge: OrderActionChallenge | null;
  error: string | null;
  notice: string | null;
  recovered: boolean;
}

interface Dependencies {
  apiClient: AxiosInstance;
  store: OrderActionStore;
  isCurrent: () => boolean;
  onSettled: (snapshot: OrderActionSnapshot) => void;
  onRecordsChanged: () => void;
  requestConfig?: AxiosRequestConfig;
}

export class OrderAction {
  record: SavedOrderAction | null;
  private state: OrderActionState = {
    attempt: 0,
    phase: 'loading',
    context: null,
    values: null,
    snapshot: null,
    challenge: null,
    error: null,
    notice: null,
    recovered: false,
  };
  private listeners = new Set<() => void>();
  private generation = 0;
  private busy = false;
  private retired = false;
  private persistenceAttempted = false;
  private requested = false;
  private known: OrderActionSnapshot | null = null;

  constructor(
    readonly owner: OrderSubmissionOwner,
    readonly orderUuid: string,
    readonly purpose: OrderActionPurpose,
    private dependencies: Dependencies,
    record: SavedOrderAction | null = null,
  ) {
    this.record = record;
    this.persistenceAttempted = !!record;
    this.requested = !!record;
  }

  getSnapshot = (): OrderActionState => this.state;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  isCurrent = (): boolean => !this.retired && this.dependencies.isCurrent();
  close = (): void => {
    this.retired = true;
    this.generation++;
  };
  private current(generation: number): boolean {
    return this.isCurrent() && generation === this.generation;
  }
  private publish(next: Partial<OrderActionState>): void {
    this.state = { ...this.state, ...next };
    for (const listener of [...this.listeners]) {
      try {
        listener();
      } catch {
        console.warn('Order action view update did not complete.');
      }
    }
  }
  private config(generation: number): AxiosRequestConfig {
    return {
      ...this.dependencies.requestConfig,
      ledovaSubmissionGuard: () => {
        if (!this.current(generation)) throw new Error('This order action view is no longer active.');
      },
    };
  }
  private async run(phase: OrderActionPhase, operation: (generation: number) => Promise<void>): Promise<void> {
    if (!this.isCurrent() || this.busy) return;
    this.busy = true;
    const generation = ++this.generation;
    this.publish({
      attempt: generation,
      phase,
      error: null,
      notice: null,
      challenge: ['loading', 'preparing'].includes(phase) ? null : this.state.challenge,
    });
    try {
      await operation(generation);
    } catch (error) {
      if (this.current(generation))
        this.publish({
          phase: !this.record && this.state.context ? 'editing' : 'error',
          challenge: null,
          error: apiErrorSentence(
            error,
            error instanceof Error ? error.message : 'The action result is unavailable. Please check its saved status.',
          ),
        });
    } finally {
      if (generation === this.generation) this.busy = false;
    }
  }

  load = (): Promise<void> => {
    if (this.record) return this.recover();
    return this.run('loading', async (generation) => {
      const response = await getOrderActionContext(
        this.dependencies.apiClient,
        this.orderUuid,
        this.owner.ownerAccountUuid,
        this.config(generation),
      );
      if (!this.current(generation)) return;
      validateOrderActionContext(response.data, this.owner.ownerAccountUuid, this.orderUuid);
      const context = response.data;
      this.publish({
        phase: 'editing',
        context,
        values: {
          quantity: context.currentValues.quantity,
          minQuantity: context.currentValues.minQuantity,
          pricePerShare: context.currentValues.pricePerShare,
        },
      });
    });
  };

  edit = (field: keyof OrderActionValues, value: string): void => {
    if (this.isCurrent() && !this.busy && !this.record && this.state.phase === 'editing' && this.state.values)
      this.publish({ values: { ...this.state.values, [field]: value }, error: null });
  };

  prepare = (): Promise<void> => {
    if (!this.state.context || !this.state.values || this.requested || !['editing', 'error'].includes(this.state.phase))
      return Promise.resolve();
    return this.run('preparing', async (generation) => {
      const context = this.state.context!;
      const replacements = this.purpose === 'modify' ? canonicalOrderActionValues(this.state.values!) : null;
      if (!this.record) this.record = this.dependencies.store.reserve(this.owner, this.orderUuid, this.purpose);
      const retry = this.persistenceAttempted;
      this.persistenceAttempted = true;
      await this.dependencies.store.persist(this.record, retry);
      if (!this.current(generation)) return;
      this.dependencies.onRecordsChanged();
      this.requested = true;
      const response = await this.message(replacements, generation);
      if (!this.current(generation)) return;
      validateOrderActionSnapshot(response.data, this.record);
      validateOrderActionIssuance(response.data, context, replacements);
      await this.accept(response, generation, false, true);
    });
  };

  private async observation(
    request: Promise<AxiosResponse<OrderActionSnapshot>>,
  ): Promise<AxiosResponse<OrderActionSnapshot>> {
    try {
      return await request;
    } catch (error) {
      const response = (error as { response?: AxiosResponse<OrderActionSnapshot> })?.response;
      if ((response?.status === 400 || response?.status === 409) && response.data?.status === 'refused')
        return response;
      throw error;
    }
  }
  private message(
    replacements: OrderActionValues | null,
    generation: number,
  ): Promise<AxiosResponse<OrderActionSnapshot>> {
    const data = { actionId: this.record!.actionId, ownerAccountUuid: this.owner.ownerAccountUuid };
    return this.observation(
      this.purpose === 'cancel'
        ? getOrderCancelMessage(this.dependencies.apiClient, this.orderUuid, data, this.config(generation))
        : getOrderModificationMessage(
            this.dependencies.apiClient,
            this.orderUuid,
            {
              ...data,
              newQuantity: replacements!.quantity,
              newMinQuantity: replacements!.minQuantity,
              newPricePerShare: replacements!.pricePerShare,
            },
            this.config(generation),
          ),
    );
  }
  private async accept(
    response: AxiosResponse<OrderActionSnapshot>,
    generation: number,
    recovered: boolean,
    pendingAllowed = false,
  ): Promise<void> {
    if (!this.current(generation)) return;
    const snapshot = response.data;
    validateOrderActionSnapshot(snapshot, this.record!, this.known);
    if (response.status !== 200 && !(snapshot.status === 'refused' && response.status === snapshot.refusal!.httpStatus))
      throw new Error('The action response did not establish an outcome.');
    if (snapshot.status === 'pending') {
      if (!pendingAllowed || !snapshot.challenge) throw new Error('A fresh action signing request is unavailable.');
      this.known = snapshot;
      this.publish({ phase: 'ready', snapshot, challenge: snapshot.challenge, error: null, recovered });
      return;
    }
    this.known = snapshot;
    this.publish({ phase: snapshot.status, snapshot, challenge: null, error: null, recovered });
    this.dependencies.onSettled(snapshot);
    if (!this.current(generation)) return;
    try {
      await this.dependencies.store.remove(this.record!);
    } catch {
      if (this.current(generation))
        this.publish({
          notice: 'This result is recorded. Its saved reminder could not be cleared; checking it again is safe.',
        });
    }
    if (this.current(generation)) this.dependencies.onRecordsChanged();
  }

  recover = (): Promise<void> => {
    if (!this.record) return this.load();
    if (!this.requested) return this.prepare();
    return this.run('preparing', async (generation) => {
      const response = await getOrderAction(
        this.dependencies.apiClient,
        this.record!.actionId,
        this.owner.ownerAccountUuid,
        this.config(generation),
      );
      if (!this.current(generation)) return;
      validateOrderActionSnapshot(response.data, this.record!, this.known);
      if (response.data.challenge !== null) throw new Error('Action recovery unexpectedly returned a signing request.');
      if (response.data.status !== 'pending') {
        await this.accept(response, generation, true);
        return;
      }
      this.known = response.data;
      const message = await this.message(response.data.intent.modifications, generation);
      await this.accept(message, generation, true, true);
    });
  };

  private async send(signature: string, generation: number): Promise<void> {
    if (!this.current(generation) || !this.state.challenge) return;
    this.publish({ phase: 'submitting' });
    const data = {
      actionId: this.record!.actionId,
      ownerAccountUuid: this.owner.ownerAccountUuid,
      digest: this.state.challenge.digest,
      signature,
    };
    const response = await this.observation(
      this.purpose === 'cancel'
        ? cancelOrder(this.dependencies.apiClient, this.orderUuid, data, this.config(generation))
        : modifyOrder(this.dependencies.apiClient, this.orderUuid, data, this.config(generation)),
    );
    await this.accept(response, generation, false);
  }
  private canSign(): boolean {
    return this.isCurrent() && !this.busy && this.state.phase === 'ready' && !!this.state.challenge;
  }
  private expired(): boolean {
    return Date.parse(this.state.challenge!.expiresAt) <= Date.now();
  }
  sign = (signer: (current: () => boolean) => Promise<string | null>): Promise<void> => {
    if (!this.canSign()) return Promise.resolve();
    if (this.expired()) return this.recover();
    return this.run('signing', async (generation) => {
      const signature = await signer(() => this.current(generation));
      if (!this.current(generation)) return;
      if (!signature) {
        this.publish({ phase: 'ready' });
        return;
      }
      await this.send(signature, generation);
    });
  };
  submitSignature = (signature: string): Promise<void> => {
    if (!this.canSign()) return Promise.resolve();
    if (this.expired()) return this.recover();
    return this.run('submitting', (generation) => this.send(signature, generation));
  };
}
