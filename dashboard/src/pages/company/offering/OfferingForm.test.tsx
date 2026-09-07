// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CompanyShareToken, OfferingInput, OperatorSettlementAsset } from '@ledova/shared';
import { OfferingForm } from './OfferingForm';

const TOKEN = { uuid: 'token-1', symbol: 'QAT', name: 'QA Token' } as unknown as CompanyShareToken;

const AUDY: OperatorSettlementAsset = {
  uuid: 'asset-audy',
  symbol: 'AUDY',
  name: 'Audy',
  chainDeployments: [{ chain: 'base', contractAddress: `0x${'9'.repeat(40)}`, decimals: 2, isActive: true }],
} as unknown as OperatorSettlementAsset;

const USDC: OperatorSettlementAsset = { ...AUDY, uuid: 'asset-usdc', symbol: 'USDC', name: 'USD Coin' };

function fillTheRequiredFields() {
  fireEvent.change(screen.getByLabelText('Price per share (AUD)'), { target: { value: '1.50' } });
  fireEvent.change(screen.getByLabelText('Minimum shares'), { target: { value: '10' } });
  fireEvent.change(screen.getByLabelText('Target shares'), { target: { value: '100' } });
  fireEvent.change(screen.getByLabelText('Cap shares'), { target: { value: '200' } });
  fireEvent.change(screen.getByLabelText('Opens at'), { target: { value: '2026-10-01T09:00' } });
}

function created(onCreate: ReturnType<typeof vi.fn>): OfferingInput {
  return onCreate.mock.calls[0][0] as OfferingInput;
}

describe('OfferingForm settlement assets', () => {
  afterEach(cleanup);

  it('offers the operator settlement assets the issuer may accept', () => {
    render(<OfferingForm tokens={[TOKEN]} busy={false} settlementAssets={[AUDY, USDC]} onCreate={vi.fn()} />);

    expect(screen.getByLabelText('AUDY')).toBeDefined();
    expect(screen.getByLabelText('USDC')).toBeDefined();
  });

  it('carries the chosen settlement assets in the payload', () => {
    const onCreate = vi.fn();
    render(<OfferingForm tokens={[TOKEN]} busy={false} settlementAssets={[AUDY, USDC]} onCreate={onCreate} />);
    fillTheRequiredFields();

    fireEvent.click(screen.getByLabelText('USDC'));
    fireEvent.click(screen.getByText('Create draft offering'));

    expect(created(onCreate).settlementAssets).toEqual(['asset-usdc']);
  });

  it('sends no settlement assets when the issuer chooses none', () => {
    const onCreate = vi.fn();
    render(<OfferingForm tokens={[TOKEN]} busy={false} settlementAssets={[AUDY]} onCreate={onCreate} />);
    fillTheRequiredFields();

    fireEvent.click(screen.getByText('Create draft offering'));

    expect(created(onCreate).settlementAssets).toEqual([]);
  });

  it('says why there is nothing to choose when the operator supports no stablecoin', () => {
    render(<OfferingForm tokens={[TOKEN]} busy={false} settlementAssets={[]} onCreate={vi.fn()} />);

    expect(screen.getByText(/operator has not configured a settlement asset/i)).toBeDefined();
  });

  it('still offers bank transfer when there is no settlement asset', () => {
    render(<OfferingForm tokens={[TOKEN]} busy={false} settlementAssets={[]} onCreate={vi.fn()} />);

    expect(screen.getByLabelText('Accept bank transfer')).toBeDefined();
  });

  it('refuses an offering with no rail at all', () => {
    const onCreate = vi.fn();
    render(<OfferingForm tokens={[TOKEN]} busy={false} settlementAssets={[AUDY]} onCreate={onCreate} />);
    fillTheRequiredFields();

    fireEvent.click(screen.getByLabelText('Accept bank transfer'));
    fireEvent.click(screen.getByText('Create draft offering'));

    expect(onCreate).not.toHaveBeenCalled();
  });
});
