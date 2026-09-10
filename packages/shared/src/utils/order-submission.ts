import type { AxiosInstance, AxiosRequestConfig } from 'axios';
import type {
  CreateOrderRequest,
  CreateOrderMessageResponse,
  OrderSubmissionRequest,
  OrderSubmissionSnapshot,
} from '../types';
import { createOrder, getOrderCreateMessage, getOrderSubmission, parseTradingError } from '../services/trading';
import type { OrderSubmissionStore, SavedOrderSubmission } from './order-submission-storage';

export type OrderSubmissionPhase = 'preparing' | 'ready' | 'signing' | 'submitting' | 'created' | 'refused' | 'error';

export interface OrderSubmissionState {
  attempt: number;
  phase: OrderSubmissionPhase;
  snapshot: OrderSubmissionSnapshot | null;
  challenge: CreateOrderMessageResponse | null;
  error: string | null;
  notice: string | null;
  recovered: boolean;
}

interface SubmissionDependencies {
  apiClient: AxiosInstance;
  store: OrderSubmissionStore;
  isCurrent: () => boolean;
  onSettled: (snapshot: OrderSubmissionSnapshot) => void;
  onRecordsChanged: () => void;
  requestConfig?: AxiosRequestConfig;
}

export class OrderSubmission {
  private state: OrderSubmissionState = {
    attempt: 0,
    phase: 'preparing',
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

  constructor(
    readonly record: SavedOrderSubmission,
    private dependencies: SubmissionDependencies,
  ) {}

  getSnapshot = (): OrderSubmissionState => this.state;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
  isCurrent = (): boolean => !this.retired && this.dependencies.isCurrent();
  close = (): void => {
    this.retired = true;
    this.generation++;
  };

  private publish(next: Partial<OrderSubmissionState>): void {
    this.state = { ...this.state, ...next };
    for (const listener of [...this.listeners]) {
      try {
        listener();
      } catch {
        console.warn('Order view update did not complete.');
      }
    }
  }

  private current(generation: number): boolean {
    return this.isCurrent() && this.generation === generation;
  }

  private config(generation: number): AxiosRequestConfig {
    return {
      ...this.dependencies.requestConfig,
      ledovaSubmissionGuard: () => {
        if (!this.current(generation))
          throw new Error('This order view is no longer active. Check its saved status to continue.');
      },
    };
  }

  private validate(snapshot: OrderSubmissionSnapshot): void {
    if (
      !snapshot ||
      snapshot.submissionId !== this.record.submissionId ||
      snapshot.ownerAccountUuid !== this.record.ownerAccountUuid ||
      snapshot.walletUuid !== this.record.walletUuid ||
      !snapshot.intent ||
      !['pending', 'created', 'refused'].includes(snapshot.status) ||
      (snapshot.status === 'created' && !snapshot.order) ||
      (snapshot.status === 'refused' && !snapshot.refusal)
    ) {
      throw new Error('The saved order response did not match this order.');
    }
    const challenge = snapshot.challenge;
    if (
      challenge &&
      (challenge.purpose !== 'order_create' ||
        challenge.message.submissionId !== this.record.submissionId ||
        challenge.message.ownerAccountUuid !== this.record.ownerAccountUuid ||
        challenge.message.walletUuid !== this.record.walletUuid)
    ) {
      throw new Error('The signing request did not match this order.');
    }
  }

  private request(snapshot: OrderSubmissionSnapshot): OrderSubmissionRequest {
    return {
      ...snapshot.intent,
      submissionId: this.record.submissionId,
      ownerAccountUuid: this.record.ownerAccountUuid,
      walletUuid: this.record.walletUuid,
    };
  }

  private async accept(snapshot: OrderSubmissionSnapshot, generation: number, recovered: boolean): Promise<void> {
    if (!this.current(generation)) return;
    this.validate(snapshot);
    if (snapshot.status === 'pending') {
      if (!snapshot.challenge) throw new Error('A fresh signing request is unavailable. Check this order again.');
      this.publish({ phase: 'ready', snapshot, challenge: snapshot.challenge, error: null, recovered });
      return;
    }
    this.dependencies.onSettled(snapshot);
    this.publish({ phase: snapshot.status, snapshot, challenge: null, error: null, recovered });
    try {
      await this.dependencies.store.remove(this.record);
    } catch {
      if (this.current(generation))
        this.publish({
          notice: 'This result is confirmed. Its saved reminder could not be cleared; checking it again is safe.',
        });
    }
    this.dependencies.onRecordsChanged();
  }

  private async run(phase: OrderSubmissionPhase, operation: (generation: number) => Promise<void>): Promise<void> {
    if (!this.isCurrent() || this.busy) return;
    this.busy = true;
    const generation = ++this.generation;
    this.publish({
      attempt: generation,
      phase,
      challenge: phase === 'preparing' ? null : this.state.challenge,
      error: null,
      notice: null,
    });
    try {
      await operation(generation);
    } catch (error) {
      if (this.current(generation)) this.publish({ phase: 'error', challenge: null, error: parseTradingError(error) });
    } finally {
      if (this.generation === generation) this.busy = false;
    }
  }

  start = (draft: CreateOrderRequest): Promise<void> =>
    this.run('preparing', async (generation) => {
      const response = await getOrderCreateMessage(
        this.dependencies.apiClient,
        {
          ...draft,
          submissionId: this.record.submissionId,
          ownerAccountUuid: this.record.ownerAccountUuid,
        },
        this.config(generation),
      );
      await this.accept(response.data, generation, response.data.status !== 'pending');
    });

  recover = (): Promise<void> =>
    this.run('preparing', async (generation) => {
      const response = await getOrderSubmission(
        this.dependencies.apiClient,
        this.record.submissionId,
        this.record.ownerAccountUuid,
        this.config(generation),
      );
      if (!this.current(generation)) return;
      this.validate(response.data);
      if (response.data.status !== 'pending') {
        await this.accept(response.data, generation, true);
        return;
      }
      const message = await getOrderCreateMessage(
        this.dependencies.apiClient,
        this.request(response.data),
        this.config(generation),
      );
      await this.accept(message.data, generation, true);
    });

  private async send(signature: string, generation: number): Promise<void> {
    if (!this.current(generation) || !this.state.snapshot || !this.state.challenge) return;
    this.publish({ phase: 'submitting' });
    try {
      const response = await createOrder(
        this.dependencies.apiClient,
        {
          ...this.request(this.state.snapshot),
          digest: this.state.challenge.digest,
          signature,
        },
        this.config(generation),
      );
      await this.accept(response.data, generation, response.status === 200);
    } catch (error) {
      const response = (error as { response?: { status?: number; data?: OrderSubmissionSnapshot } })?.response;
      if (response?.status === 400 && response.data?.status === 'refused') {
        await this.accept(response.data, generation, false);
      } else throw error;
    }
  }

  private canSign(): boolean {
    return this.isCurrent() && !this.busy && this.state.phase === 'ready' && !!this.state.challenge;
  }

  private expired(): boolean {
    const expiry = Date.parse(this.state.challenge?.expiresAt ?? '');
    return !Number.isFinite(expiry) || expiry <= Date.now();
  }

  sign = (signer: (isCurrent: () => boolean) => Promise<string | null>): Promise<void> => {
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
