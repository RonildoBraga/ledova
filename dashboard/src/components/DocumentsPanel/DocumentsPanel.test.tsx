// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import apiClient from '@services/apiClient';
import type { Document } from '../../types/document';
import { DocumentsPanel } from './DocumentsPanel';

vi.mock('@services/apiClient', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }));

const claim = {
  uuid: '12345678-1111-4111-8111-111111111111',
  categoryDisplay: 'Professional investor',
  status: 'submitted',
};
const document: Document = {
  uuid: '87654321-1111-4111-8111-111111111111',
  documentType: 'payslip',
  originalFilename: 'synthetic-payslip.pdf',
  mimeType: 'application/pdf',
  note: '',
  classification: null,
  attachedAt: null,
  retentionUntil: '2026-10-09T00:00:00Z',
  purgedAt: null,
  fileUrl: '/private-document/',
  latestExtraction: null,
  createdAt: '2026-09-09T00:00:00Z',
  updatedAt: '2026-09-09T00:00:00Z',
};
let client: QueryClient;
let mode: string;
let rows: Document[];

beforeEach(() => {
  vi.clearAllMocks();
  mode = 'registry';
  rows = [{ ...document }];
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  vi.mocked(apiClient.get).mockImplementation(async (url) => {
    if (url === '/api/operator/') return { data: { deploymentMode: mode } };
    if (url === '/api/investor-classifications/') return { data: { results: [claim] } };
    if (url === '/api/v1/documents/') return { data: { results: rows } };
    return { data: rows[0] };
  });
});

afterEach(() => {
  cleanup();
  client.clear();
});

function showPanel() {
  return render(
    <QueryClientProvider client={client}>
      <DocumentsPanel />
    </QueryClientProvider>,
  );
}

describe('supporting payslips', () => {
  it('does not render or fetch payslips in single-issuer mode', async () => {
    mode = 'single_issuer';
    const view = showPanel();
    await waitFor(() => expect(client.getQueryState(['operator'])?.status).toBe('success'));
    expect(view.container.textContent).toBe('');
    expect(vi.mocked(apiClient.get).mock.calls.map(([url]) => url)).toEqual(['/api/operator/']);
  });

  it('keeps the store hidden when the deployment mode cannot be loaded', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('operator unavailable'));
    const view = showPanel();
    await waitFor(() => expect(client.getQueryState(['operator'])?.status).toBe('error'));
    expect(view.container.textContent).toBe('');
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it('attaches a payslip to the selected existing claim and removes its delete control', async () => {
    vi.mocked(apiClient.post).mockImplementation(async () => {
      rows = [{ ...document, classification: claim.uuid, attachedAt: '2026-09-09T00:00:00Z', retentionUntil: null }];
      return { data: rows[0] };
    });
    showPanel();
    expect(await screen.findByText('synthetic-payslip.pdf')).toBeTruthy();
    expect(screen.getByText(/does not establish eligibility/)).toBeTruthy();
    await screen.findByRole('option', { name: /Professional investor/ });
    fireEvent.change(screen.getByLabelText('Classification claim'), { target: { value: claim.uuid } });
    fireEvent.click(screen.getByRole('button', { name: 'Attach to claim' }));
    await screen.findByText(/Attached to claim 12345678/);
    expect(apiClient.post).toHaveBeenCalledWith(`/api/v1/documents/${document.uuid}/attach/`, {
      classification: claim.uuid,
    });
    expect(screen.queryByTitle('Delete document')).toBeNull();
  });

  it('sends the selected claim with a new payslip upload', async () => {
    rows = [];
    vi.mocked(apiClient.post).mockResolvedValue({ data: { ...document, classification: claim.uuid } });
    const view = showPanel();
    await screen.findByText('Click to upload a payslip');
    const file = new File(['%PDF-1.4 synthetic'], 'new-payslip.pdf', { type: 'application/pdf' });
    fireEvent.change(view.container.querySelector('input[type="file"]')!, { target: { files: [file] } });
    await screen.findByRole('option', { name: /Professional investor/ });
    fireEvent.change(screen.getByLabelText('Classification claim'), { target: { value: claim.uuid } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload & extract' }));
    await waitFor(() => expect(apiClient.post).toHaveBeenCalled());
    const [url, payload] = vi.mocked(apiClient.post).mock.calls[0];
    expect(url).toBe('/api/v1/documents/');
    expect((payload as FormData).get('classification')).toBe(claim.uuid);
    expect((payload as FormData).get('file')).toBe(file);
  });

  it('shows an attachment refusal without marking the document as retained', async () => {
    vi.mocked(apiClient.post).mockRejectedValue({
      response: { status: 400, data: { detail: 'This claim has already been reviewed.' } },
    });
    showPanel();
    await screen.findByRole('option', { name: /Professional investor/ });
    fireEvent.change(screen.getByLabelText('Classification claim'), { target: { value: claim.uuid } });
    fireEvent.click(screen.getByRole('button', { name: 'Attach to claim' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'This claim has already been reviewed.');
    expect(screen.queryByText(/Attached to claim/)).toBeNull();
    expect(screen.getByTitle('Delete document')).toBeTruthy();
  });
});
