import { act, renderHook, waitFor } from '@testing-library/react-native';
import EventSource from 'react-native-sse';
import { useTradingEvents } from './useTradingEvents';
import { getAccessToken } from '../../../services/tokenStorage';

const mockInvalidateQueries = jest.fn();
const mockQueryClient = { invalidateQueries: mockInvalidateQueries };
const mockEventListeners = new Map<string, () => void>();

jest.mock('../../../services/tokenStorage', () => ({ getAccessToken: jest.fn(async () => 'synthetic-access') }));
jest.mock('@tanstack/react-query', () => ({ useQueryClient: () => mockQueryClient }));
jest.mock('react-native-sse', () =>
  jest.fn().mockImplementation(() => ({
    addEventListener: jest.fn((type: string, listener: () => void) => mockEventListeners.set(type, listener)),
    close: jest.fn(),
  })),
);

beforeEach(() => mockEventListeners.clear());

it('opens an authenticated stream on the validated API origin', async () => {
  process.env.EXPO_PUBLIC_API_URL = 'https://api.example.test';
  const view = await renderHook(() => useTradingEvents('synthetic&other=value'));
  await waitFor(() => expect(EventSource).toHaveBeenCalledTimes(1));
  const [url, options] = jest.mocked(EventSource).mock.calls[0];
  expect(new URL(String(url)).origin).toBe('https://api.example.test');
  expect(new URL(String(url)).searchParams.get('token')).toBe('synthetic&other=value');
  expect(options?.headers).toEqual({ Authorization: 'Bearer synthetic-access' });
  await view.unmount();
});

it('refuses a public HTTP stream before reading credentials or creating a connection', async () => {
  process.env.EXPO_PUBLIC_API_URL = 'http://api.example.test';
  const view = await renderHook(() => useTradingEvents('synthetic'));
  await act(async () => {});
  expect(getAccessToken).not.toHaveBeenCalled();
  expect(EventSource).not.toHaveBeenCalled();
  await view.unmount();
});

it('refreshes reserved orders and signing views when a swap expires', async () => {
  process.env.EXPO_PUBLIC_API_URL = 'https://api.example.test';
  const view = await renderHook(() => useTradingEvents('synthetic'));
  await waitFor(() => expect(EventSource).toHaveBeenCalledTimes(1));
  expect(mockEventListeners.has('swap_expired')).toBe(true);
  await act(() => mockEventListeners.get('swap_expired')?.());
  expect(mockInvalidateQueries.mock.calls).toEqual([
    [{ queryKey: ['trading', 'orderBook'] }],
    [{ queryKey: ['trading', 'userOrders'] }],
    [{ queryKey: ['trading', 'swaps'] }],
    [{ queryKey: ['trading', 'orderSwapData'] }],
  ]);
  await view.unmount();
});
